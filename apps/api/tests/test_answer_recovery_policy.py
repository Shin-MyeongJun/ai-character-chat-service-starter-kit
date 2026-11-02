"""Durable recovery policy against real SQLite writes; PG locking is tested separately."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, TimeoutError
from test_generation_completion_contracts import Backend
from test_generation_completion_contracts import backend as backend

from app.db.models.product_usage import AnswerRecoveryAttempt, ProductGeneration
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat.service.command import answer_recovery as Recovery
from app.modules.chatting.chat.service.workflow import answers as Workflow


def audit(item: Backend) -> list[AnswerRecoveryAttempt]:
    return list(
        item.store.scalars(
            select(AnswerRecoveryAttempt).order_by(AnswerRecoveryAttempt.attempt_count)
        )
    )


def due(item: Backend) -> None:
    item.change(answer_recovery_next_at=datetime.now(UTC) - timedelta(seconds=1))


@pytest.mark.asyncio
async def test_budget_survives_restart_and_replay_cannot_bypass_cooldown_or_quarantine(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = backend
    original_metadata = dict(item.state().answer_metadata)
    failure = TimeoutError("private database pool details")
    for count in range(1, Types.ANSWER_RECOVERY_MAX_ATTEMPTS + 1):
        # A new runtime each attempt shares only database state.
        runtime = Workflow.AnswerOrchestrator(
            item.sessions, item.orchestrator.text, item.orchestrator.retriever
        )
        finalize = AsyncMock(side_effect=failure)
        monkeypatch.setattr(runtime, "_finalize", finalize)
        with pytest.raises(Types.AnswerStorageError):
            await runtime._complete_staged(
                item.generation_id, item.owner_id, recover=True
            )
        assert item.state().answer_recovery_attempts == count
        assert len(audit(item)) == count
        assert audit(item)[-1].failure_class == "storage_unavailable"
        assert await runtime.recover_answers() == 0
        with pytest.raises(Types.AnswerStorageError):
            await runtime._resume(
                PersistenceMapper.generation_entity_to_state_info(item.state())
            )
        assert finalize.await_count == 1
        if count < Types.ANSWER_RECOVERY_MAX_ATTEMPTS:
            assert item.state().answer_recovery_quarantined_at is None
        due(item)
    assert item.state().answer_recovery_quarantined_at is not None
    assert item.state().status == "pending"
    assert item.state().answer_metadata == original_metadata
    assert (
        item.effect_count("credit")
        == item.effect_count("usage")
        == item.effect_count("memory")
        == 0
    )
    assert await runtime.recover_answers() == 0
    with pytest.raises(Types.AnswerStorageError):
        await runtime._complete_staged(item.generation_id, item.owner_id, recover=True)
    assert item.state().answer_recovery_attempts == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,failure_class",
    [
        (Types.AnswerStateError("private invariant"), "invariant"),
        (TypeError("private internal error"), "internal"),
        (
            IntegrityError("private SQL", {}, RuntimeError("private constraint")),
            "storage_constraint",
        ),
    ],
)
async def test_deterministic_failures_quarantine_first_attempt(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    failure_class: str,
) -> None:
    item = backend
    monkeypatch.setattr(item.orchestrator, "_finalize", AsyncMock(side_effect=error))
    with pytest.raises(Types.AnswerStorageError) as caught:
        await item.orchestrator._complete_staged(
            item.generation_id, item.owner_id, recover=True
        )
    assert caught.value.__cause__ is error
    assert item.state().answer_recovery_attempts == 1
    assert item.state().answer_recovery_quarantined_at is not None
    assert audit(item)[0].failure_class == failure_class
    due(item)
    assert await item.orchestrator.recover_answers() == 0


@pytest.mark.asyncio
async def test_claim_is_committed_before_finalize_and_cancellation_consumes_attempt(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = backend

    async def cancel(*args: object, **kwargs: object) -> Types.AnswerInfo:
        assert item.state().answer_recovery_attempts == 1
        assert len(audit(item)) == 1 and item.events[-1] == "commit"
        raise asyncio.CancelledError()

    monkeypatch.setattr(item.orchestrator, "_finalize", cancel)
    with pytest.raises(asyncio.CancelledError):
        await item.orchestrator._complete_staged(
            item.generation_id, item.owner_id, recover=True
        )
    assert item.state().status == "pending"
    assert item.state().answer_recovery_attempts == 1
    assert await item.orchestrator.recover_answers() == 0


@pytest.mark.asyncio
async def test_lost_claim_ack_never_finalizes_without_confirmed_admission(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = backend
    original = Recovery.claim_answer_recovery

    async def lost_ack(
        session: object, command: Types.ClaimAnswerRecoveryCommand
    ) -> Types.AnswerRecoveryClaimInfo:
        await original(session, command)
        raise RuntimeError("private commit acknowledgement")

    monkeypatch.setattr(Recovery, "claim_answer_recovery", lost_ack)
    finalize = AsyncMock()
    monkeypatch.setattr(item.orchestrator, "_finalize", finalize)
    with pytest.raises(Types.AnswerStorageError):
        await item.orchestrator._complete_staged(
            item.generation_id, item.owner_id, recover=True
        )
    finalize.assert_not_awaited()
    assert item.state().answer_recovery_attempts == 1 and len(audit(item)) == 1


@pytest.mark.asyncio
async def test_manual_attempt_is_audited_preserves_budget_and_reconciles_once(
    backend: Backend,
) -> None:
    item = backend
    now = datetime.now(UTC)
    item.change(
        answer_recovery_attempts=5,
        answer_recovery_quarantined_at=now,
        answer_recovery_next_at=now + timedelta(minutes=1),
    )
    command = Types.ClaimAnswerRecoveryCommand(
        generation_id=item.generation_id,
        user_id=item.owner_id,
        now=now,
        operator="ops-123",
        reason="Investigated billing binding; repaired configuration.",
    )
    with pytest.raises(Types.AnswerStorageError):
        await item.orchestrator.recover_answer(command)
    assert item.state().answer_recovery_attempts == 5 and audit(item) == []
    due(item)
    answer = await item.orchestrator.recover_answer(command)
    assert answer.status == "succeeded" and answer.content == "Output"
    assert item.state().answer_recovery_attempts == 6
    assert item.state().answer_recovery_quarantined_at is not None
    assert len(audit(item)) == 1
    assert (
        audit(item)[0].operator == command.operator
        and audit(item)[0].reason == command.reason
    )
    assert (
        item.effect_count("credit")
        == item.effect_count("usage")
        == item.effect_count("memory")
        == 1
    )
    # Terminal replay returns stored facts and creates no further recovery audit.
    item.executed.clear()
    assert await item.orchestrator.recover_answer(command) == answer
    assert not any(
        sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in item.executed
    )
    assert len(audit(item)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operator,reason",
    [
        (None, None),
        ("", "check"),
        ("ops", " "),
        ("ops", None),
        (None, "check"),
        ("x" * 121, "check"),
        ("ops", "x" * 1001),
    ],
)
async def test_manual_requires_bounded_operator_and_reason_without_state_change(
    backend: Backend,
    operator: str | None,
    reason: str | None,
) -> None:
    item = backend
    with pytest.raises(ValueError):
        await item.orchestrator.recover_answer(
            Types.ClaimAnswerRecoveryCommand(
                generation_id=item.generation_id,
                user_id=item.owner_id,
                now=datetime.now(UTC),
                operator=operator,
                reason=reason,
            )
        )
    assert item.state().answer_recovery_attempts == 0 and audit(item) == []


@pytest.mark.asyncio
async def test_quarantine_does_not_starve_other_due_answers(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = backend
    values = dict(
        item.store.execute(select(ProductGeneration.__table__)).mappings().one()
    )
    good_id = uuid4()
    item.store.add(
        ProductGeneration(**{**values, "id": good_id, "request_key": "other-answer"})
    )
    item.store.commit()
    bad_metadata = dict(item.state().answer_metadata)
    bad_metadata.pop("billing")
    item.change(answer_metadata=bad_metadata)

    async def usage(session: object, command: object) -> None:
        await session.execute(item.effects.insert().values(kind="usage", cost=0))

    monkeypatch.setattr(
        Workflow.GenerationCommandService.BillingService, "record_usage", usage
    )
    assert await item.orchestrator.recover_answers() == 2
    assert (
        item.state().status == "pending"
        and item.state().answer_recovery_quarantined_at is not None
    )
    good = item.store.get(ProductGeneration, good_id, populate_existing=True)
    assert good.status == "succeeded"
    assert item.effect_count("credit") == 1
    due(item)
    assert await item.orchestrator.recover_answers() == 0


@pytest.mark.asyncio
async def test_failure_record_error_cannot_replenish_committed_budget(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = backend
    monkeypatch.setattr(
        item.orchestrator,
        "_finalize",
        AsyncMock(side_effect=TimeoutError("private pool error")),
    )
    monkeypatch.setattr(
        Recovery,
        "record_answer_recovery_failure",
        AsyncMock(side_effect=TimeoutError("private record error")),
    )
    with pytest.raises(Types.AnswerStorageError):
        await item.orchestrator._complete_staged(
            item.generation_id, item.owner_id, recover=True
        )
    assert item.state().answer_recovery_attempts == 1 and len(audit(item)) == 1
    assert await item.orchestrator.recover_answers() == 0


@pytest.mark.asyncio
async def test_old_failure_cannot_quarantine_newer_attempt_or_terminal_state(
    backend: Backend,
) -> None:
    item = backend
    now = datetime.now(UTC)
    command = Types.ClaimAnswerRecoveryCommand(
        generation_id=item.generation_id, user_id=item.owner_id, now=now
    )
    async with item.sessions() as session:
        first = await Recovery.claim_answer_recovery(session, command)
    due(item)
    async with item.sessions() as session:
        second = await Recovery.claim_answer_recovery(
            session, replace(command, now=now + timedelta(seconds=1))
        )
    assert first.attempt_count == 1 and second.attempt_count == 2
    failure = Types.RecordAnswerRecoveryFailureCommand(
        generation_id=item.generation_id,
        user_id=item.owner_id,
        attempt_count=1,
        failure_class="internal",
        now=now,
    )
    async with item.sessions() as session:
        await Recovery.record_answer_recovery_failure(session, failure)
    assert item.state().answer_recovery_quarantined_at is None
    await item.orchestrator._complete_staged(item.generation_id, item.owner_id)
    async with item.sessions() as session:
        await Recovery.record_answer_recovery_failure(
            session, replace(failure, attempt_count=2)
        )
    assert item.state().answer_recovery_quarantined_at is None
    assert (
        item.store.scalar(select(func.count()).select_from(AnswerRecoveryAttempt)) == 2
    )
