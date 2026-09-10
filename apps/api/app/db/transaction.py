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
