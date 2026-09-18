# 여러 Command가 같은 세션에서 이 컨텍스트를 중첩하면 최외곽에서 한 번 커밋한다.
# 안쪽 예외를 호출자가 잡아도 failed가 남아 전체 트랜잭션을 롤백한다. savepoint는 만들지 않는다.
# 이 범위 밖에서 이미 autobegin된 세션은 채택하지 않으므로 SQLAlchemy가 시작 오류를 낸다.
"""Explicitly composed use cases share one transaction and rollback-only state."""

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

_STATE_KEY = "application_use_case_transaction"


@asynccontextmanager
async def use_case_transaction(session: AsyncSession):
    """Join an application scope, never silently take ownership of autobegin.

    A caller with an existing transaction must explicitly enter this scope before
    invoking commands. A nested failure poisons the scope even if it is caught.
    """
    state = session.info.get(_STATE_KEY)
    if state is not None:
        try:
            yield
        except BaseException:
            state["failed"] = True
            raise
        return

    state = {"failed": False}
    # begin() deliberately rejects an unrelated active/autobegun transaction.
    async with session.begin():
        session.info[_STATE_KEY] = state
        try:
            yield
            if state["failed"]:
                raise RuntimeError("A nested use case failed; transaction rolled back.")
        finally:
            session.info.pop(_STATE_KEY, None)
