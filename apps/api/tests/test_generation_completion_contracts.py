"""Offline completion SQL counts and transaction boundaries, not PostgreSQL locks."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    JSON,
    Column,
    Connection,
    Integer,
    MetaData,
    Select,
    Table,
    Text,
    Uuid,
    create_engine,
    event,
    func,
    select,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, attributes

from app.db.models.chat import Conversation, ConversationCharacter, Message
from app.db.models.product_usage import AnswerRecoveryAttempt, ProductGeneration
from app.db.types import SessionFactory
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import answers as AnswersCommand
from app.modules.chatting.chat.service.command import generation as Command
from app.modules.chatting.chat.service.workflow import answers as Workflow
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import types as ProductTypes
from app.modules.llm.service import EmbeddingService, TextGenerationService


@dataclass
class Backend:
    store: Session
    sessions: SessionFactory
    orchestrator: Workflow.AnswerOrchestrator
    generation_id: UUID
    owner_id: UUID
    conversation_id: UUID
    slot_id: UUID
    effects: Table
    statements: list[str]
    executed: list[str]
    events: list[str]
    failure: str | None = None

    def value(self) -> Types.GenerationResult:
        return Types.GenerationResult(
            11, 7, 9, (Types.GeneratedMessage(self.slot_id, "Output"),)
        )

    def command(
        self, value: Types.GenerationResult | None = None
    ) -> Types.FinishGenerationCommand:
        return Types.FinishGenerationCommand(
            generation_id=self.generation_id,
            user_id=self.owner_id,
            value=value or self.value(),
        )

    def state(self) -> ProductGeneration:
        entity = self.store.get(
            ProductGeneration, self.generation_id, populate_existing=True
        )
        assert entity is not None
        return entity

    def effect_count(self, kind: str) -> int:
        return (
            self.store.scalar(
                select(func.count())
                .select_from(self.effects)
                .where(self.effects.c.kind == kind)
            )
            or 0
        )

    def change(self, **fields: object) -> None:
        self.store.execute(
            update(ProductGeneration)
            .where(ProductGeneration.id == self.generation_id)
            .values(**fields)
        )
        self.store.commit()
        self.statements.clear()
        self.executed.clear()
        self.events.clear()


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    defaults = {
        "id": "(lower(hex(randomblob(16))))",
        "created_at": "CURRENT_TIMESTAMP",
        "updated_at": "CURRENT_TIMESTAMP",
        "revision": "1",
        "generated_by_ai": "false",
    }
    from sqlalchemy import text

    for model in (
        Conversation,
        ConversationCharacter,
        Message,
        ProductGeneration,
        AnswerRecoveryAttempt,
    ):
        Table(
            model.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else JSON()
                    if isinstance(column.type, JSONB)
                    else column.type,
                    primary_key=column.primary_key,
                    server_default=text(defaults[column.name])
                    if column.name in defaults
                    else None,
                )
                for column in model.__table__.columns
            ),
        )
    effects = Table(
        "completion_effects",
        metadata,
        Column("kind", Text, primary_key=True),
        Column("cost", Integer),
    )
    metadata.create_all(engine)
    statements: list[str] = []
    executed: list[str] = []
    events: list[str] = []

    def sql_executed(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        executed.append(statement)

    event.listen(engine, "before_cursor_execute", sql_executed)
    try:
        with Session(engine, expire_on_commit=False) as store:
            owner, conversation_id, product, snapshot, model_id, generation, slot = [
                uuid4() for _ in range(7)
            ]
            now = datetime.now(UTC)
            metadata_value: Types.AnswerMetadata = {
                "version": 2,
                "phase": "result_ready",
                "execution_token": "worker",
                "identity": {"product_character_id": str(slot)},
                "outcome": "succeeded",
                "content": "Output",
                "usage": {"input_tokens": 11, "output_tokens": 7},
                "billing": {
                    "request_key": str(uuid4()),
                    "reservation_id": str(uuid4()),
                    "reserved_credit": 9,
                },
            }
            store.add_all(
                [
                    Conversation(
                        id=conversation_id,
                        user_id=owner,
                        product_id=product,
                        product_snapshot_id=snapshot,
                        initial_snapshot_id=snapshot,
                        title="Work",
                        is_group=False,
                        opening_mode="snapshot",
                        history_revision=1,
                        created_at=now,
                        updated_at=now,
                    ),
                    ConversationCharacter(
                        id=uuid4(),
                        conversation_id=conversation_id,
                        product_character_id=slot,
                        role_order=0,
                        joined_at=now,
                    ),
                    ProductGeneration(
                        id=generation,
                        user_id=owner,
                        conversation_id=conversation_id,
                        product_id=product,
                        product_snapshot_id=snapshot,
                        model_id=model_id,
                        model_name="model",
                        reasoning_effort="medium",
                        request_key="answer",
                        input_digest="input",
                        status="pending",
                        message_count=0,
                        created_at=now,
                        answer_metadata=metadata_value,
                        answer_lease_until=now - timedelta(seconds=1),
                    ),
                ]
            )
            store.commit()
            store.expunge_all()
            position = 0

            def assign_test_identity(
                session: Session, flush_context: object, instances: object
            ) -> None:
                nonlocal position
                # SQLite has no PostgreSQL identity sequence. Only test inserts are adapted.
                for entity in session.new:
                    if isinstance(entity, Message):
                        position += 1
                        entity.id = entity.id or uuid4()
                        entity.position = position

            event.listen(store, "before_flush", assign_test_identity)

            def scalars(statement: Select[tuple[object, ...]]) -> ScalarResult[object]:
                statements.append(str(statement.compile(dialect=postgresql.dialect())))
                return store.scalars(statement)

            def scalar(statement: Select[tuple[object, ...]]) -> object:
                statements.append(str(statement.compile(dialect=postgresql.dialect())))
                return store.scalar(statement)

            def committed(session: Session) -> None:
                store.commit()
                events.append("commit")

            def rolled_back(session: Session) -> None:
                store.rollback()
                events.append("rollback")

            @asynccontextmanager
            async def sessions() -> AsyncIterator[AsyncSession]:
                async with AsyncSession() as session:
                    event.listen(session.sync_session, "after_commit", committed)
                    event.listen(session.sync_session, "after_rollback", rolled_back)
                    for name, operation in (
                        ("scalars", scalars),
                        ("scalar", scalar),
                        ("execute", store.execute),
                        ("get", store.get),
                        ("flush", store.flush),
                    ):
                        monkeypatch.setattr(
                            session, name, AsyncMock(side_effect=operation)
                        )
                    monkeypatch.setattr(session, "add", store.add)
                    yield session

            orchestrator = Workflow.AnswerOrchestrator(
                sessions,
                TextGenerationService(()),
                MemoryService.MemoryRetriever(sessions, EmbeddingService(())),
            )
            item = Backend(
                store,
                sessions,
                orchestrator,
                generation,
                owner,
                conversation_id,
                slot,
                effects,
                statements,
                executed,
                events,
            )
            original_get = Command.Repository.get_owned_generation

            async def get_generation(
                session: AsyncSession,
                generation_id: UUID,
                user_id: UUID,
                *,
                lock: bool = False,
            ) -> ProductGeneration | None:
                entity = await original_get(session, generation_id, user_id, lock=lock)
                if entity is not None:
                    # SQLite drops tzinfo. Restore only the production UTC representation.
                    for name in (
                        "answer_lease_until",
                        "answer_recovery_next_at",
                        "answer_recovery_quarantined_at",
                    ):
                        instant = getattr(entity, name)
                        if instant is not None:
                            attributes.set_committed_value(
                                entity, name, instant.replace(tzinfo=UTC)
                            )
                return entity

            async def effect(session: AsyncSession, kind: str, cost: int = 0) -> None:
                assert session.in_transaction()
                await session.execute(effects.insert().values(kind=kind, cost=cost))
                if item.failure == kind:
                    raise RuntimeError(kind + " failed")

            async def usage(
                session: AsyncSession, command: BillingTypes.RecordUsageCommand
            ) -> None:
                assert command.user_id == owner and command.generation_id == generation
                await effect(session, "usage", command.cost_credit)

            async def statistics(
                session: AsyncSession, command: ProductTypes.MarkStatisticsDirtyCommand
            ) -> None:
                assert command.product_id == product
                await effect(session, "statistics")

            async def memory(
                session: AsyncSession, command: MemoryTypes.ScheduleMemoryWorkCommand
            ) -> None:
                assert (
                    command.conversation_id == conversation_id
                    and command.owner_id == owner
                )
                await effect(session, "memory")

            async def settle(
                session: AsyncSession,
                command: BillingTypes.CommitCreditReservationCommand
                | BillingTypes.ReleaseCreditReservationCommand,
            ) -> BillingTypes.CreditReservationInfo:
                committed = isinstance(
                    command, BillingTypes.CommitCreditReservationCommand
                )
                await effect(session, "credit", 9 if committed else 0)
                return BillingTypes.CreditReservationInfo(
                    id=command.reservation_id,
                    user_id=command.user_id,
                    request_key=command.request_key,
                    quote_id=uuid4(),
                    status=BillingTypes.CreditReservationStatus.COMMITTED
                    if committed
                    else BillingTypes.CreditReservationStatus.RELEASED,
                    reserved_credit=10 if item.failure == "amount" else 9,
                    result_id=generation if committed else None,
                )

            monkeypatch.setattr(
                Command.Repository, "get_owned_generation", get_generation
            )
            monkeypatch.setattr(Command, "ensure_available", AsyncMock())
            monkeypatch.setattr(Command.BillingService, "record_usage", usage)
            monkeypatch.setattr(Command, "mark_statistics_dirty", statistics)
            monkeypatch.setattr(Workflow.MemoryService, "schedule_memory_work", memory)
            monkeypatch.setattr(
                Workflow.BillingCreditService, "commit_credit_reservation", settle
            )
            monkeypatch.setattr(
                Workflow.BillingCreditService, "release_credit_reservation", settle
            )
            statements.clear()
            executed.clear()
            yield item
    finally:
        engine.dispose()


def assert_completion_reads(
    item: Backend, generation_reads: int = 2, conversation_locks: int = 1
) -> None:
    generation_selects = [
        sql
        for sql in item.executed
        if sql.lstrip().upper().startswith("SELECT")
        and "FROM product_generations" in sql
    ]
    assert len(generation_selects) == generation_reads
    assert (
        sum(
            "FROM conversations" in sql and "FOR UPDATE" in sql
            for sql in item.statements
        )
        == conversation_locks
    )
    if generation_reads == 2:
        assert (
            sum(
                "FROM product_generations" in sql and "FOR UPDATE" in sql
                for sql in item.statements
            )
            == 1
        )


@pytest.mark.asyncio
async def test_finalize_reuses_locked_state_and_completion_then_replays_without_side_effects(
    backend: Backend,
) -> None:
    item = backend
    result = await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert (
        result.status == "succeeded"
        and result.content == "Output"
        and result.price_credit == 9
    )
    assert_completion_reads(item)
    assert item.events == ["commit"]
    assert item.state().message_count == 1
    assert item.state().answer_lease_until is None
    assert item.store.scalar(select(func.count()).select_from(Message)) == 1
    for kind in ("usage", "statistics", "memory", "credit"):
        assert item.effect_count(kind) == 1
    item.store.rollback()
    item.executed.clear()
    item.statements.clear()
    item.events.clear()
    assert (
        await item.orchestrator._finalize(item.generation_id, item.owner_id) == result
    )
    assert_completion_reads(item)
    assert item.effect_count("memory") == 1 and item.effect_count("credit") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("with_memory", [False, True])
async def test_public_completion_entry_points_keep_checks_and_digest_replay(
    backend: Backend, with_memory: bool
) -> None:
    item = backend
    finish = (
        Workflow.finish_generation_and_schedule_memory
        if with_memory
        else Command.finish_generation
    )
    async with item.sessions() as session:
        result = await finish(session, item.command())
    assert result.status == "succeeded"
    assert_completion_reads(item)
    assert item.state().answer_lease_until is None
    assert item.effect_count("memory") == int(with_memory)
    item.store.rollback()
    async with item.sessions() as session:
        assert await finish(session, item.command()) == result
    assert item.effect_count("usage") == 1 and item.effect_count("memory") == int(
        with_memory
    )
    item.store.rollback()
    async with item.sessions() as session:
        with pytest.raises(ValueError, match="different output"):
            await finish(session, item.command(replace(item.value(), cost_credit=8)))
    assert item.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled", "switched", "expired"])
async def test_non_success_keeps_usage_but_releases_without_output_or_success_queue(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    if status in {"failed", "cancelled"}:
        metadata_value["outcome"] = status
        item.change(answer_metadata=metadata_value)
    elif status == "switched":
        item.store.execute(
            update(Conversation)
            .where(Conversation.id == item.conversation_id)
            .values(product_snapshot_id=uuid4())
        )
        item.store.commit()
        item.executed.clear()
        item.statements.clear()
    else:
        item.store.rollback()
        item.executed.clear()
        item.statements.clear()
        monkeypatch.setattr(
            Command,
            "ensure_available",
            AsyncMock(side_effect=ValueError("Version expired.")),
        )
    result = await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert result.status == (status if status in {"failed", "cancelled"} else "stale")
    assert_completion_reads(item)
    assert item.state().answer_lease_until is None
    assert item.store.scalar(select(func.count()).select_from(Message)) == 0
    assert item.effect_count("usage") == item.effect_count("credit") == 1
    assert item.effect_count("memory") == 0
    assert (
        item.store.scalar(
            select(item.effects.c.cost).where(item.effects.c.kind == "credit")
        )
        == 0
    )
    assert (
        item.store.scalar(
            select(item.effects.c.cost).where(item.effects.c.kind == "usage")
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["usage", "statistics", "memory", "credit", "amount"]
)
async def test_downstream_failure_rolls_back_all_effects_and_staged_result_can_recover(
    backend: Backend, failure: str
) -> None:
    item = backend
    item.failure = failure
    lease_before = item.state().answer_lease_until
    assert lease_before is not None
    with pytest.raises((RuntimeError, Types.AnswerStorageError)):
        await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert item.events == ["rollback"]
    assert item.state().status == "pending"
    assert item.state().answer_lease_until == lease_before
    stored_metadata = item.state().answer_metadata
    assert stored_metadata is not None and stored_metadata["phase"] == "result_ready"
    assert item.store.scalar(select(func.count()).select_from(Message)) == 0
    assert item.store.scalar(select(func.count()).select_from(item.effects)) == 0
    item.store.rollback()
    item.failure = None
    result = await item.orchestrator._finalize(
        item.generation_id, item.owner_id, recover=True
    )
    assert result.status == "succeeded" and result.content == "Output"
    assert item.state().answer_lease_until is None
    assert (
        item.effect_count("memory")
        == item.effect_count("usage")
        == item.effect_count("credit")
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["preparing", "calling"])
async def test_expired_lease_recovery_updates_metadata_in_same_lock_scope_without_reread(
    backend: Backend, phase: str
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    metadata_value["phase"] = phase
    metadata_value.pop("outcome", None)
    metadata_value.pop("content", None)
    item.change(answer_metadata=metadata_value)
    result = await item.orchestrator._finalize(
        item.generation_id, item.owner_id, recover=True
    )
    assert result.status == "failed"
    assert result.error_code == (
        "interrupted_uncertain" if phase == "calling" else "interrupted_before_call"
    )
    assert result.uncertain is (phase == "calling")
    assert_completion_reads(item)
    assert item.state().answer_lease_until is None
    stored_metadata = item.state().answer_metadata
    assert stored_metadata is not None and stored_metadata["phase"] == "result_ready"
    assert item.effect_count("credit") == 1 and item.effect_count("memory") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("lease", [None, "future"])
async def test_recovery_does_not_finalize_live_or_legacy_unleased_execution(
    backend: Backend, lease: str | None
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    metadata_value["phase"] = "calling"
    item.change(
        answer_metadata=metadata_value,
        answer_lease_until=datetime.now(UTC) + timedelta(days=1) if lease else None,
    )
    assert (
        await item.orchestrator._finalize(
            item.generation_id, item.owner_id, recover=True
        )
    ).status == "pending"
    assert_completion_reads(item)
    assert item.store.scalar(select(func.count()).select_from(item.effects)) == 0


@pytest.mark.asyncio
async def test_wrong_owner_fails_before_conversation_lock_or_any_write(
    backend: Backend,
) -> None:
    item = backend
    with pytest.raises(LookupError, match="Generation not found"):
        await item.orchestrator._finalize(item.generation_id, uuid4())
    assert_completion_reads(item, generation_reads=1, conversation_locks=0)
    assert item.events == ["rollback"]


@pytest.mark.asyncio
async def test_invalid_direct_result_is_rejected_before_database_reads(
    backend: Backend,
) -> None:
    async with backend.sessions() as session:
        with pytest.raises(ValueError, match="Usage must"):
            await Command.finish_generation(
                session, backend.command(replace(backend.value(), cost_credit=-1))
            )
    assert backend.executed == [] and backend.statements == []


@pytest.mark.asyncio
async def test_closed_lock_scope_cannot_be_reused(backend: Backend) -> None:
    item = backend
    async with item.sessions() as session:
        async with Command._locked_generation(
            session,
            Types.GetGenerationStateCommand(
                generation_id=item.generation_id, user_id=item.owner_id
            ),
        ) as locked:
            pass
        with pytest.raises(RuntimeError, match="no longer active"):
            await Workflow._finish_locked_generation_and_schedule_memory(
                locked, item.value()
            )
    assert item.effect_count("usage") == 0


@pytest.mark.asyncio
async def test_caught_memory_error_poisoning_still_prevents_outer_commit(
    backend: Backend,
) -> None:
    item = backend
    item.failure = "memory"
    async with item.sessions() as session:
        with pytest.raises(RuntimeError, match="nested use case failed"):
            async with Command._locked_generation(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=item.generation_id, user_id=item.owner_id
                ),
            ) as locked:
                with pytest.raises(RuntimeError, match="memory failed"):
                    await Workflow._finish_locked_generation_and_schedule_memory(
                        locked, item.value()
                    )
    assert item.events == ["rollback"]
    assert item.state().status == "pending" and item.effect_count("usage") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    ["token", "expired", "live_recovery", "immutable", "durable", "terminal", "none"],
)
async def test_answer_update_public_entry_keeps_writer_and_lease_guards(
    backend: Backend, invalid: str
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    metadata_value["phase"] = "result_ready" if invalid == "durable" else "calling"
    lease = datetime.now(UTC) + timedelta(days=1)
    item.change(
        answer_metadata=metadata_value,
        answer_lease_until=lease,
        status="succeeded" if invalid == "terminal" else "pending",
    )
    updated = {**metadata_value, "phase": "result_ready"}
    if invalid == "immutable":
        updated["provider"] = "changed-provider"
    if invalid == "durable":
        updated["content"] = "changed-result"
    if invalid == "expired":
        item.change(answer_lease_until=datetime.now(UTC) - timedelta(days=1))
    command = Types.UpdateAnswerCommand(
        generation_id=item.generation_id,
        user_id=item.owner_id,
        metadata=updated,
        lease_until=lease,
        execution_token="wrong" if invalid == "token" else "worker",
        recover=invalid == "live_recovery",
    )
    async with item.sessions() as session:
        if invalid == "none":
            await AnswersCommand.update_answer(session, command)
        else:
            with pytest.raises(Types.MessageConflictError):
                await AnswersCommand.update_answer(session, command)
    assert_completion_reads(item)
    stored = item.state().answer_metadata
    assert stored == (updated if invalid == "none" else metadata_value)
    assert item.effect_count("usage") == 0


@pytest.mark.asyncio
async def test_terminal_change_before_generation_lock_is_reread_without_writing(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = backend
    original_owned = Command.get_owned_conversation

    async def owned(
        session: AsyncSession,
        command: Command.ConversationTypes.OwnedConversationCommand,
    ) -> Command.ConversationTypes.ConversationInfo:
        conversation = await original_owned(session, command)
        # Exercise the gap between routing lookup and the locked generation read.
        await session.execute(
            update(ProductGeneration)
            .where(ProductGeneration.id == item.generation_id)
            .values(status="failed", result_digest="other-result")
        )
        return conversation

    monkeypatch.setattr(Command, "get_owned_conversation", owned)
    result = await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert result.status == "failed"
    assert_completion_reads(item)
    assert item.effect_count("usage") == item.effect_count("memory") == 0


@pytest.mark.asyncio
async def test_missing_billing_binding_still_rejects_success_before_finishing(
    backend: Backend,
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    metadata_value.pop("billing", None)
    metadata_value["unbilled_reason"] = "preparation_failed"
    item.change(answer_metadata=metadata_value)
    with pytest.raises(
        Types.AnswerStorageError, match="Missing answer billing binding"
    ):
        await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert item.state().status == "pending" and item.effect_count("usage") == 0


@pytest.mark.asyncio
async def test_unbilled_summary_failure_schedules_recovery_without_charge(
    backend: Backend,
) -> None:
    item = backend
    metadata_value = dict(item.state().answer_metadata or {})
    metadata_value.pop("billing", None)
    metadata_value.update(
        outcome="failed",
        unbilled_reason="preparation_failed",
        error_code="summary_required",
        retryable=True,
    )
    item.change(answer_metadata=metadata_value)
    result = await item.orchestrator._finalize(item.generation_id, item.owner_id)
    assert (
        result.status == "failed"
        and result.error_code == "summary_required"
        and result.retryable
    )
    assert_completion_reads(item)
    assert item.effect_count("memory") == item.effect_count("usage") == 1
    assert item.effect_count("credit") == 0
