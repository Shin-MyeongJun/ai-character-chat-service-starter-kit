"""Whole-work deadlines, cleanup, retry classification and shutdown cancellation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app import memory_worker
from app.db.models.memory import MemoryJob
from app.db.types import SessionFactory
from app.modules.chatting.chat.service.workflow import memory as Workflow
from app.modules.chatting.chat.types import ProcessMemoryWorkCommand
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.service.command.scheduling import fail_memory_work
from app.modules.llm.types import LLMError, LLMErrorKind, LLMProvider


def command(timeout_seconds: float = 0.02) -> ProcessMemoryWorkCommand:
    return ProcessMemoryWorkCommand(
        work=Types.MemoryWorkInfo(
            uuid4(), uuid4(), 1, 1, "worker", claim_token=uuid4()
        ),
        policy=Types.MemoryPolicy(),
        models=Types.MemoryModelConfig(
            summary_provider="mock",
            summary_model="summary",
            embedding_provider="voyage",
            embedding_model="voyage-large-2",
        ),
        timeout_seconds=timeout_seconds,
    )


@pytest.mark.asyncio
async def test_expired_timeout_rejects_result_before_clock_reaches_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timer = asyncio.timeout(60)
    # Model a timer fired within clock resolution and swallowed cancellation.
    # The wall clock comparison alone would still allow this result to be saved.
    monkeypatch.setattr(timer, "expired", lambda: True)
    with pytest.raises(Types.MemoryWorkDeadlineExceededError):
        Workflow._check_work_deadline(timer)


@pytest.fixture
def failure_recorder(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    record = AsyncMock()
    monkeypatch.setattr(Workflow.MemoryService, "fail_memory_work", record)
    return record


@pytest.mark.asyncio
async def test_deadline_cancels_work_closes_session_then_records_failure(
    monkeypatch: pytest.MonkeyPatch, failure_recorder: AsyncMock
) -> None:
    events: list[str] = []

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            try:
                yield session
            finally:
                events.append("session_closed")

    async def execute(
        session_factory: SessionFactory, *args: object, **kwargs: object
    ) -> None:
        async with session_factory():
            try:
                await asyncio.Event().wait()
            finally:
                events.append("operation_stopped")

    async def record(*args: object) -> None:
        assert events == ["operation_stopped", "session_closed"]
        events.append("failure_recorded")

    failure_recorder.side_effect = record
    monkeypatch.setattr(Workflow, "_process_memory_work", execute)
    request = command()
    with pytest.raises(TimeoutError):
        await Workflow.process_memory_work(
            sessions, request, summary_generator=object(), indexer=object()
        )
    recorded = failure_recorder.await_args.args[1]
    assert recorded.work == request.work and recorded.retryable
    assert recorded.error_kind == "MemoryWorkDeadlineExceededError"
    assert events[-2:] == ["failure_recorded", "session_closed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["internal", "provider", "request_timeout"])
async def test_work_failure_keeps_original_exception_and_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
    failure_recorder: AsyncMock,
    failure_kind: str,
) -> None:
    failures = {
        "internal": TypeError("malformed response"),
        "provider": LLMError(
            "SDK programming failure",
            kind=LLMErrorKind.PROVIDER,
            provider=LLMProvider.OPENAI,
            model="gpt-test",
            retryable=False,
        ),
        "request_timeout": TimeoutError("request timeout"),
    }
    failure = failures[failure_kind]
    monkeypatch.setattr(
        Workflow, "_process_memory_work", AsyncMock(side_effect=failure)
    )
    with pytest.raises(type(failure)) as caught:
        await Workflow.process_memory_work(
            AsyncSession, command(1), summary_generator=object(), indexer=object()
        )
    assert caught.value is failure
    recorded = failure_recorder.await_args.args[1]
    assert recorded.retryable is (failure_kind == "request_timeout")
    assert recorded.error_kind == (
        "provider" if failure_kind == "provider" else type(failure).__name__
    )


@pytest.mark.asyncio
async def test_shutdown_cancellation_drains_work_without_recording_retry(
    monkeypatch: pytest.MonkeyPatch, failure_recorder: AsyncMock
) -> None:
    entered, stopped = asyncio.Event(), asyncio.Event()

    async def execute(*args: object, **kwargs: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(Workflow, "_process_memory_work", execute)
    task = asyncio.create_task(
        Workflow.process_memory_work(
            AsyncSession, command(10), summary_generator=object(), indexer=object()
        )
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    failure_recorder.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [0, -1, float("nan"), float("inf"), True])
async def test_invalid_deadline_rejected_before_work_or_failure_write(
    monkeypatch: pytest.MonkeyPatch,
    failure_recorder: AsyncMock,
    timeout_seconds: float,
) -> None:
    execute = AsyncMock()
    monkeypatch.setattr(Workflow, "_process_memory_work", execute)
    with pytest.raises(ValueError, match="timeout_seconds"):
        await Workflow.process_memory_work(
            AsyncSession,
            command(timeout_seconds),
            summary_generator=object(),
            indexer=object(),
        )
    execute.assert_not_awaited()
    failure_recorder.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lease,timeout", [(300, "300"), (100, "240"), (300, "nan"), (0, "1")]
)
async def test_worker_rejects_unsafe_deadline_before_initializing_resources(
    monkeypatch: pytest.MonkeyPatch, lease: int, timeout: str
) -> None:
    monkeypatch.setenv("MEMORY_WORK_LEASE_SECONDS", str(lease))
    monkeypatch.setenv("MEMORY_WORK_TIMEOUT_SECONDS", timeout)
    create = Mock()
    monkeypatch.setattr(memory_worker, "create_async_engine", create)
    with pytest.raises(ValueError, match="MEMORY_WORK"):
        await memory_worker.run_worker(once=True, concurrency=1, poll_seconds=0.01)
    create.assert_not_called()


def summary(request: ProcessMemoryWorkCommand) -> Types.MemoryInfo:
    return Types.MemoryInfo(
        id=uuid4(),
        conversation_id=request.work.conversation_id,
        memory_type="summary",
        content="existing summary",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        conversation_revision=1,
    )


def prepare_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    read = AsyncMock(return_value=(SimpleNamespace(history_revision=1), (), False))
    persist, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(Workflow, "_read_unsummarized", read)
    monkeypatch.setattr(Workflow, "_persist_summary", persist)
    monkeypatch.setattr(Workflow, "_complete", complete)
    monkeypatch.setattr(
        Workflow.MemoryService,
        "plan_summarization",
        Mock(return_value=SimpleNamespace(source_end_position=1)),
    )
    return read, persist, complete


@pytest.mark.asyncio
async def test_deadline_is_shared_by_pending_index_and_new_summary(
    monkeypatch: pytest.MonkeyPatch, failure_recorder: AsyncMock
) -> None:
    request = command(0.2)
    read, persist, complete = prepare_workflow(monkeypatch)
    existing = summary(request)
    monkeypatch.setattr(
        Workflow, "_read_pending_index", AsyncMock(return_value=existing)
    )

    async def index(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(0.12)

    async def generate(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.12)
        return object()

    monkeypatch.setattr(Workflow, "_index_summary", AsyncMock(side_effect=index))
    generate_call = AsyncMock(side_effect=generate)
    with pytest.raises(Types.MemoryWorkDeadlineExceededError):
        await Workflow.process_memory_work(
            AsyncSession,
            request,
            summary_generator=SimpleNamespace(generate_summary=generate_call),
            indexer=object(),
        )
    read.assert_awaited_once()
    generate_call.assert_awaited_once()
    persist.assert_not_awaited()
    complete.assert_not_awaited()
    assert failure_recorder.await_args.args[1].retryable


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["summary", "embedding"])
async def test_late_provider_result_after_suppressed_cancellation_is_not_saved(
    monkeypatch: pytest.MonkeyPatch, failure_recorder: AsyncMock, stage: str
) -> None:
    request = command()
    read, persist, complete = prepare_workflow(monkeypatch)
    existing = summary(request)
    monkeypatch.setattr(
        Workflow,
        "_read_pending_index",
        AsyncMock(return_value=existing if stage == "embedding" else None),
    )

    async def late_result(*args: object, **kwargs: object) -> object:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return object()

    generate = AsyncMock(side_effect=late_result)
    embed = AsyncMock(side_effect=late_result)
    save_embedding = AsyncMock()
    monkeypatch.setattr(
        Workflow.MemoryService, "save_summary_embedding", save_embedding
    )
    with pytest.raises(Types.MemoryWorkDeadlineExceededError):
        await Workflow.process_memory_work(
            AsyncSession,
            request,
            summary_generator=SimpleNamespace(generate_summary=generate),
            indexer=SimpleNamespace(embed_summary=embed),
        )
    persist.assert_not_awaited()
    save_embedding.assert_not_awaited()
    complete.assert_not_awaited()
    assert failure_recorder.await_args.args[1].retryable
    if stage == "embedding":
        read.assert_not_awaited()
        generate.assert_not_awaited()
    else:
        embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_work_keeps_normal_completion(
    monkeypatch: pytest.MonkeyPatch, failure_recorder: AsyncMock
) -> None:
    request = command(1)
    _, persist, complete = prepare_workflow(monkeypatch)
    monkeypatch.setattr(Workflow, "_read_pending_index", AsyncMock(return_value=None))
    monkeypatch.setattr(
        Workflow.MemoryService, "plan_summarization", Mock(return_value=None)
    )
    await Workflow.process_memory_work(
        AsyncSession, request, summary_generator=object(), indexer=object()
    )
    complete.assert_awaited_once_with(AsyncSession, request.work, more_work=False)
    persist.assert_not_awaited()
    failure_recorder.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt_count,retryable,status",
    [(1, True, "pending"), (5, True, "failed"), (1, False, "failed")],
)
async def test_actual_failure_queue_retains_backoff_limit_and_new_requests(
    monkeypatch: pytest.MonkeyPatch, attempt_count: int, retryable: bool, status: str
) -> None:
    request = command(1)
    request = replace(request, work=replace(request.work, attempt_count=attempt_count))
    engine = create_engine("sqlite://")
    MemoryJob.__table__.create(engine)
    try:
        with Session(engine) as store:
            store.add(
                MemoryJob(
                    conversation_id=request.work.conversation_id,
                    owner_id=request.work.owner_id,
                    requested_generation=2,
                    completed_generation=0,
                    scope_generation=1,
                    status="running",
                    attempt_count=attempt_count,
                    lease_owner="worker",
                    claim_token=request.work.claim_token,
                    leased_until=datetime.now(UTC),
                )
            )
            store.commit()

            @asynccontextmanager
            async def sessions() -> AsyncIterator[AsyncSession]:
                async with AsyncSession() as session:
                    monkeypatch.setattr(
                        session, "scalar", AsyncMock(side_effect=store.scalar)
                    )
                    yield session

            failure = (
                Types.MemoryWorkDeadlineExceededError("total budget exhausted")
                if retryable
                else LLMError(
                    "SDK internal failure",
                    kind=LLMErrorKind.PROVIDER,
                    provider=LLMProvider.OPENAI,
                    model="gpt-test",
                    retryable=False,
                )
            )
            monkeypatch.setattr(
                Workflow, "_process_memory_work", AsyncMock(side_effect=failure)
            )
            monkeypatch.setattr(
                Workflow.MemoryService, "fail_memory_work", fail_memory_work
            )
            before = datetime.now(UTC)
            with pytest.raises(type(failure)):
                await Workflow.process_memory_work(
                    sessions, request, summary_generator=object(), indexer=object()
                )
            after = datetime.now(UTC)
            store.commit()
            row = store.get(MemoryJob, request.work.conversation_id)
            assert row is not None and row.status == status
            assert row.requested_generation == 2 and row.completed_generation == 0
            assert row.scope_generation is None and row.lease_owner is None
            assert row.leased_until is None and row.attempt_count == attempt_count
            assert row.last_error_kind == (
                "MemoryWorkDeadlineExceededError" if retryable else "provider"
            )
            delay = 5 * 2 ** (attempt_count - 1)
            elapsed = (row.next_attempt_at.replace(tzinfo=UTC) - before).total_seconds()
            assert delay <= elapsed <= delay + (after - before).total_seconds()
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_worker_passes_configured_budget_to_each_work_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORY_WORK_LEASE_SECONDS", "10")
    monkeypatch.setenv("MEMORY_WORK_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    engine = SimpleNamespace(dispose=AsyncMock())
    text, embedding = (
        SimpleNamespace(aclose=AsyncMock()),
        SimpleNamespace(aclose=AsyncMock()),
    )
    monkeypatch.setattr(memory_worker, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        memory_worker, "async_sessionmaker", Mock(return_value=AsyncSession)
    )
    monkeypatch.setattr(memory_worker, "_text_service", Mock(return_value=text))
    monkeypatch.setattr(memory_worker, "VoyageEmbeddingAdapter", Mock())
    monkeypatch.setattr(memory_worker, "EmbeddingService", Mock(return_value=embedding))
    work = command().work
    claim = AsyncMock(side_effect=[work, None, None])
    process = AsyncMock()
    monkeypatch.setattr(memory_worker.MemoryService, "claim_memory_work", claim)
    monkeypatch.setattr(memory_worker, "process_memory_work", process)
    await memory_worker.run_worker(once=True, concurrency=1, poll_seconds=0.01)
    assert process.await_args.args[1].timeout_seconds == 2.5
    assert all(call.args[1].lease_seconds == 10 for call in claim.await_args_list)
    text.aclose.assert_awaited_once()
    embedding.aclose.assert_awaited_once()
    engine.dispose.assert_awaited_once()
