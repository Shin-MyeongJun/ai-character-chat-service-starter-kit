# 대화별 기억 작업 예약·claim·완료·실패 경계. 재시도 지연은 초 단위이며 기본 5초부터 최대 300초다.
from datetime import UTC, datetime

from app.db.transaction import use_case_transaction
from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper


async def schedule_memory_work(
    session, command: Types.ScheduleMemoryWorkCommand
) -> None:
    async with use_case_transaction(session):
        if not await Repository.conversation_is_owned(
            session,
            conversation_id=command.conversation_id,
            owner_id=command.owner_id,
        ):
            raise LookupError("Conversation not found.")
        await Repository.schedule_memory_work(
            session,
            conversation_id=command.conversation_id,
            owner_id=command.owner_id,
            now=datetime.now(UTC),
        )


# 실행 가능하거나 lease가 만료된 작업 하나를 획득한다. 없으면 None이며 외부 호출은 하지 않는다.
async def claim_memory_work(
    session, command: Types.ClaimMemoryWorkCommand
) -> Types.MemoryWorkInfo | None:
    if not command.worker_id.strip() or len(command.worker_id) > 200:
        raise ValueError("Worker id must be 1-200 nonblank characters.")
    if not 1 <= command.lease_seconds <= 3600:
        raise ValueError("Lease seconds must be between 1 and 3600.")
    async with use_case_transaction(session):
        row = await Repository.claim_memory_work(
            session,
            worker_id=command.worker_id,
            now=datetime.now(UTC),
            lease_seconds=command.lease_seconds,
        )
        return PersistenceMapper.memory_job_entity_to_work(row)


# claim의 worker와 scope가 여전히 일치할 때 완료한다. 그 뒤 쌓인 요청 세대는 다음 처리로 남긴다.
async def complete_memory_work(
    session, command: Types.CompleteMemoryWorkCommand
) -> None:
    async with use_case_transaction(session):
        await Repository.complete_memory_work(
            session,
            work=command.work,
            more_work=command.more_work,
            now=datetime.now(UTC),
        )


# 재시도 가능 여부와 최대 시도 횟수로 pending/backoff 또는 failed를 기록한다.
async def fail_memory_work(session, command: Types.FailMemoryWorkCommand) -> None:
    if not command.error_kind.strip():
        raise ValueError("A nonblank normalized error kind is required.")
    if (
        command.max_attempts < 1
        or command.base_retry_seconds < 1
        or command.max_retry_seconds < 1
    ):
        raise ValueError("Retry limits must be positive.")
    exponent = max(0, command.work.attempt_count - 1)
    delay = min(command.max_retry_seconds, command.base_retry_seconds * (2**exponent))
    async with use_case_transaction(session):
        await Repository.fail_memory_work(
            session,
            work=command.work,
            retryable=command.retryable,
            max_attempts=command.max_attempts,
            retry_seconds=delay,
            error_kind=command.error_kind,
            now=datetime.now(UTC),
        )
