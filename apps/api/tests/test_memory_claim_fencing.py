"""Real PostgreSQL claim ownership and delayed memory workflow results."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.chat import Conversation, Message
from app.db.models.identity import User
from app.db.models.memory import ConversationMemory, MemoryJob
from app.db.models.product import Product
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat.service.workflow.memory import process_memory_work
from app.modules.chatting.chat.types import ProcessMemoryWorkCommand
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as Types
from app.modules.llm import types as LLMTypes

pytestmark = pytest.mark.asyncio


async def seed_conversation(db: AsyncSession) -> tuple[UUID, UUID]:
    owner_id, product_id, conversation_id = uuid4(), uuid4(), uuid4()
    async with use_case_transaction(db):
        db.add(User(id=owner_id, email=f"fence-{owner_id}@test.local"))
        await db.flush()
        db.add(Product(id=product_id, owner_id=owner_id, title="Fencing"))
        await db.flush()
        db.add(
            Conversation(id=conversation_id, user_id=owner_id, product_id=product_id)
        )
        await db.flush()
        db.add_all(
            Message(
                conversation_id=conversation_id, sender_type="user", content="x" * 80
            )
            for _ in range(4)
        )
    await MemoryService.schedule_memory_work(
        db,
        Types.ScheduleMemoryWorkCommand(
            conversation_id=conversation_id, owner_id=owner_id
        ),
    )
    return conversation_id, owner_id


async def claim(
    db: AsyncSession, worker_id: str = "same-process"
) -> Types.MemoryWorkInfo:
    work = await MemoryService.claim_memory_work(
        db, Types.ClaimMemoryWorkCommand(worker_id=worker_id, lease_seconds=300)
    )
    assert work is not None
    return work


async def expire(db: AsyncSession, conversation_id: UUID) -> None:
    async with use_case_transaction(db):
        await db.execute(
            update(MemoryJob)
            .where(MemoryJob.conversation_id == conversation_id)
            .values(leased_until=datetime.now(UTC) - timedelta(seconds=1))
        )


@pytest.mark.parametrize("action", ["complete", "fail"])
async def test_reclaimed_same_worker_rejects_stale_terminal_write(
    db: AsyncSession, action: Literal["complete", "fail"]
) -> None:
    conversation_id, owner_id = await seed_conversation(db)
    previous = await claim(db)
    await expire(db, conversation_id)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as other:
        current = await claim(other)
    assert previous.lease_owner == current.lease_owner
    assert previous.scope_generation == current.scope_generation
    assert previous.claim_token != current.claim_token
    await MemoryService.schedule_memory_work(
        db,
        Types.ScheduleMemoryWorkCommand(
            conversation_id=conversation_id, owner_id=owner_id
        ),
    )
    if action == "complete":
        await MemoryService.complete_memory_work(
            db, Types.CompleteMemoryWorkCommand(work=previous)
        )
    else:
        await MemoryService.fail_memory_work(
            db,
            Types.FailMemoryWorkCommand(
                work=previous, retryable=False, error_kind="old_attempt"
            ),
        )
    async with factory() as observer:
        job = await observer.get(MemoryJob, conversation_id)
        assert job is not None
        assert job.status == "running"
        assert job.attempt_count == current.attempt_count
        assert job.completed_generation == 0 and job.requested_generation == 2
        assert job.last_error_kind is None
        assert job.claim_token == current.claim_token
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=current)
    )
    async with factory() as observer:
        job = await observer.scalar(select(MemoryJob))
        assert job is not None and job.status == "pending"
        assert job.completed_generation == 1 and job.requested_generation == 2
        assert job.claim_token is None


class Generator(MemoryService.SummaryGenerator):
    def __init__(
        self, during_call: Callable[[], Awaitable[None]] | None = None
    ) -> None:
        self.during_call = during_call
        self.calls = 0

    async def generate_summary(
        self, command: Types.GenerateSummaryCommand
    ) -> Types.GeneratedSummaryInfo:
        self.calls += 1
        if self.during_call is not None:
            await self.during_call()
        return Types.GeneratedSummaryInfo(
            plan=command.plan,
            content="durable summary",
            provider=LLMTypes.LLMProvider.MOCK,
            model="summary",
            input_tokens=10,
            output_tokens=2,
        )


class Indexer(MemoryService.MemoryIndexer):
    def __init__(
        self, during_call: Callable[[], Awaitable[None]] | None = None
    ) -> None:
        self.during_call = during_call
        self.calls = 0

    async def embed_summary(
        self, command: Types.EmbedSummaryCommand
    ) -> Types.EmbeddedSummaryInfo:
        self.calls += 1
        if self.during_call is not None:
            await self.during_call()
        return Types.EmbeddedSummaryInfo(
            memory_id=command.memory_id,
            conversation_id=command.conversation_id,
            owner_id=command.owner_id,
            content_digest=command.content_digest,
            conversation_revision=command.conversation_revision,
            vector=(1.0,) * 1536,
            provider=LLMTypes.EmbeddingProvider.VOYAGE,
            model="embedding",
            dimension=1536,
            settings={"purpose": "document"},
            total_tokens=3,
        )


def process_command(work: Types.MemoryWorkInfo) -> ProcessMemoryWorkCommand:
    return ProcessMemoryWorkCommand(
        work=work,
        policy=Types.MemoryPolicy(
            summarization_threshold_tokens=80,
            summary_batch_tokens=50,
            recent_raw_tokens=20,
        ),
        models=Types.MemoryModelConfig(
            summary_provider="mock",
            summary_model="summary",
            embedding_provider="voyage",
            embedding_model="embedding",
        ),
    )


@pytest.mark.parametrize("stage", ["summary", "embedding"])
@pytest.mark.parametrize("replacement", ["reclaim", "recreate"])
async def test_late_workflow_result_cannot_save_or_fail_replacement_claim(
    db: AsyncSession, stage: str, replacement: str
) -> None:
    conversation_id, owner_id = await seed_conversation(db)
    previous = await claim(db)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    current: Types.MemoryWorkInfo | None = None

    async def replace_claim() -> None:
        nonlocal current
        async with factory() as other:
            if replacement == "reclaim":
                await expire(other, conversation_id)
            else:
                async with use_case_transaction(other):
                    await other.execute(
                        delete(MemoryJob).where(
                            MemoryJob.conversation_id == conversation_id
                        )
                    )
                await MemoryService.schedule_memory_work(
                    other,
                    Types.ScheduleMemoryWorkCommand(
                        conversation_id=conversation_id, owner_id=owner_id
                    ),
                )
            current = await claim(other)
            assert current.claim_token != previous.claim_token
            assert current.scope_generation == previous.scope_generation
            assert current.lease_owner == previous.lease_owner

    with pytest.raises(Types.StaleMemoryWorkError, match="claim no longer owns"):
        await process_memory_work(
            factory,
            process_command(previous),
            summary_generator=Generator(replace_claim if stage == "summary" else None),
            indexer=Indexer(replace_claim if stage == "embedding" else None),
        )
    assert current is not None
    async with factory() as observer:
        job = await observer.get(MemoryJob, conversation_id)
        assert job is not None and job.status == "running"
        assert job.claim_token == current.claim_token and job.last_error_kind is None
        memories = list(await observer.scalars(select(ConversationMemory)))
        assert len(memories) == (1 if stage == "embedding" else 0)
        assert all(
            item.index_status == "pending" and item.embedding is None
            for item in memories
        )

    generator, indexer = Generator(), Indexer()
    await process_memory_work(
        factory, process_command(current), summary_generator=generator, indexer=indexer
    )
    assert generator.calls == (0 if stage == "embedding" else 1)
    assert indexer.calls == 1
    async with factory() as observer:
        job = await observer.get(MemoryJob, conversation_id)
        assert job is not None and job.status == "idle" and job.claim_token is None
        memories = list(await observer.scalars(select(ConversationMemory)))
        assert len(memories) == 1 and memories[0].index_status == "ready"
        assert (
            memories[0].summary_input_tokens == 10 and memories[0].embedding_tokens == 3
        )


async def generated_summary(
    db: AsyncSession, work: Types.MemoryWorkInfo
) -> Types.GeneratedSummaryInfo:
    async with use_case_transaction(db):
        messages = tuple(
            await db.scalars(
                select(Message)
                .where(Message.conversation_id == work.conversation_id)
                .order_by(Message.position)
            )
        )
    plan = MemoryService.plan_summarization(
        Types.PlanSummarizationCommand(
            conversation_id=work.conversation_id,
            owner_id=work.owner_id,
            conversation_revision=1,
            messages=tuple(
                Types.SourceMessageInfo(
                    item.id,
                    item.sender_type,
                    item.content,
                    item.position,
                    item.revision,
                )
                for item in messages
            ),
            policy=process_command(work).policy,
        )
    )
    assert plan is not None
    return await Generator().generate_summary(
        Types.GenerateSummaryCommand(
            plan=plan, provider="mock", model="summary", max_output_tokens=50
        )
    )


async def lock_conversation(session: AsyncSession, work: Types.MemoryWorkInfo) -> None:
    await ConversationService.get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=work.conversation_id, user_id=work.owner_id, lock=True
        ),
    )


@pytest.mark.parametrize("commit", [True, False])
async def test_result_lock_serializes_reclaim_until_commit_or_rollback(
    db: AsyncSession, commit: bool
) -> None:
    conversation_id, _ = await seed_conversation(db)
    previous = await claim(db)
    generated = await generated_summary(db, previous)
    await expire(db, conversation_id)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as writer:
        transaction = await writer.begin()
        await lock_conversation(writer, previous)
        await MemoryService.save_summary(
            writer, Types.SaveSummaryCommand(generated=generated, work=previous)
        )
        # Expiry makes the row eligible, but SKIP LOCKED cannot replace a claim
        # while its validated result is still in an uncommitted transaction.
        async with factory() as contender:
            assert (
                await MemoryService.claim_memory_work(
                    contender, Types.ClaimMemoryWorkCommand(worker_id="same-process")
                )
                is None
            )
        if commit:
            await transaction.commit()
        else:
            await transaction.rollback()
    async with factory() as contender:
        current = await claim(contender)
    assert current.claim_token != previous.claim_token
    async with factory() as observer:
        memories = list(await observer.scalars(select(ConversationMemory)))
        assert len(memories) == int(commit)


async def test_two_concurrent_claimers_get_distinct_conversations(
    db: AsyncSession,
) -> None:
    first, _ = await seed_conversation(db)
    second, _ = await seed_conversation(db)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as locked, factory() as other:
        async with use_case_transaction(locked):
            one = await claim(locked)
            two = await asyncio.wait_for(claim(other), timeout=5)
            assert {one.conversation_id, two.conversation_id} == {first, second}
            assert one.claim_token != two.claim_token


@pytest.mark.parametrize(
    "field", ["claim_token", "owner_id", "scope_generation", "lease_owner"]
)
async def test_wrong_claim_identity_cannot_store_or_change_state(
    db: AsyncSession, field: str
) -> None:
    conversation_id, _ = await seed_conversation(db)
    current = await claim(db)
    generated = await generated_summary(db, current)
    if field == "claim_token":
        wrong = replace(current, claim_token=uuid4())
    elif field == "owner_id":
        wrong = replace(current, owner_id=uuid4())
    elif field == "scope_generation":
        wrong = replace(current, scope_generation=current.scope_generation + 1)
    else:
        wrong = replace(current, lease_owner="different-worker")
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=wrong)
    )
    await MemoryService.fail_memory_work(
        db, Types.FailMemoryWorkCommand(work=wrong, error_kind="stale", retryable=True)
    )
    with pytest.raises(Types.StaleMemoryWorkError):
        async with use_case_transaction(db):
            await lock_conversation(db, current)
            await MemoryService.save_summary(
                db, Types.SaveSummaryCommand(generated=generated, work=wrong)
            )
    async with use_case_transaction(db):
        job = await db.get(MemoryJob, conversation_id, populate_existing=True)
        assert (
            job is not None
            and job.status == "running"
            and job.claim_token == current.claim_token
        )
        assert not list(await db.scalars(select(ConversationMemory)))


async def test_reclaim_committed_while_old_result_waits_rechecks_token(
    db: AsyncSession,
) -> None:
    conversation_id, _ = await seed_conversation(db)
    previous = await claim(db)
    generated = await generated_summary(db, previous)
    await expire(db, conversation_id)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    started = asyncio.Event()
    writer_pid: int | None = None

    async def late_write() -> None:
        nonlocal writer_pid
        async with factory() as writer, use_case_transaction(writer):
            await lock_conversation(writer, previous)
            writer_pid = await writer.scalar(text("SELECT pg_backend_pid()"))
            started.set()
            await MemoryService.save_summary(
                writer, Types.SaveSummaryCommand(generated=generated, work=previous)
            )

    async with factory() as reclaimer:
        async with use_case_transaction(reclaimer):
            current = await claim(reclaimer)
            task = asyncio.create_task(late_write())
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                # Observe an actual PostgreSQL lock wait, rather than assuming
                # task scheduling or a fixed sleep means the statements overlap.
                async with factory() as observer:
                    async with asyncio.timeout(5):
                        while not await observer.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": writer_pid},
                        ):
                            await asyncio.sleep(0.01)
                assert not task.done()
            except BaseException:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise
    with pytest.raises(Types.StaleMemoryWorkError):
        await asyncio.wait_for(task, timeout=5)
    async with factory() as observer:
        job = await observer.get(MemoryJob, conversation_id)
        assert job is not None and job.claim_token == current.claim_token
        assert not list(await observer.scalars(select(ConversationMemory)))


@pytest.mark.parametrize("stage", ["summary", "embedding"])
async def test_history_invalidation_still_rejects_late_results(
    db: AsyncSession, stage: str
) -> None:
    conversation_id, owner_id = await seed_conversation(db)
    previous = await claim(db)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    current: Types.MemoryWorkInfo | None = None

    async def invalidate_and_schedule() -> None:
        nonlocal current
        async with factory() as other:
            await MemoryService.invalidate_conversation_memories(
                other,
                Types.InvalidateConversationMemoriesCommand(
                    conversation_id=conversation_id, owner_id=owner_id
                ),
            )
            await MemoryService.schedule_memory_work(
                other,
                Types.ScheduleMemoryWorkCommand(
                    conversation_id=conversation_id, owner_id=owner_id
                ),
            )
            current = await claim(other)

    with pytest.raises(Types.StaleMemoryWorkError, match="[Hh]istory"):
        await process_memory_work(
            factory,
            process_command(previous),
            summary_generator=Generator(
                invalidate_and_schedule if stage == "summary" else None
            ),
            indexer=Indexer(invalidate_and_schedule if stage == "embedding" else None),
        )
    assert current is not None
    async with factory() as observer:
        job = await observer.get(MemoryJob, conversation_id)
        assert job is not None and job.claim_token == current.claim_token
        assert job.status == "running" and job.last_error_kind is None
        assert not list(await observer.scalars(select(ConversationMemory)))


async def test_failed_attempt_gets_fresh_token_and_keeps_retry_accounting(
    db: AsyncSession,
) -> None:
    conversation_id, _ = await seed_conversation(db)
    previous = await claim(db)
    await MemoryService.fail_memory_work(
        db,
        Types.FailMemoryWorkCommand(
            work=previous, error_kind="timeout", retryable=True
        ),
    )
    async with use_case_transaction(db):
        job = await db.get(MemoryJob, conversation_id, populate_existing=True)
        assert job is not None and job.claim_token is None
        assert job.status == "pending" and job.attempt_count == 1
        assert job.last_error_kind == "timeout"
        job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    current = await claim(db)
    assert current.claim_token != previous.claim_token and current.attempt_count == 2
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=current, more_work=True)
    )
    next_work = await claim(db)
    assert next_work.claim_token != current.claim_token
    assert (
        next_work.attempt_count == 1
        and next_work.scope_generation == current.scope_generation
    )


async def test_rolled_back_claim_cannot_change_later_claim(db: AsyncSession) -> None:
    await seed_conversation(db)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    with pytest.raises(RuntimeError, match="abort claim"):
        async with factory() as aborted, use_case_transaction(aborted):
            previous = await claim(aborted)
            raise RuntimeError("abort claim")
    current = await claim(db)
    assert current.attempt_count == previous.attempt_count == 1
    assert current.claim_token != previous.claim_token
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=previous)
    )
    async with factory() as observer:
        job = await observer.get(MemoryJob, current.conversation_id)
        assert (
            job is not None
            and job.status == "running"
            and job.claim_token == current.claim_token
        )
