"""U18 PostgreSQL claims, budget, manual reconciliation and migration parity."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, func, select, text, update
from sqlalchemy.exc import DBAPIError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from test_nonstream_answers import setup_answer

from app.db.models.billing import UsageLog
from app.db.models.chat import Message
from app.db.models.memory import MemoryJob
from app.db.models.product_usage import AnswerRecoveryAttempt, ProductGeneration
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import answer_recovery as Recovery
from app.modules.chatting.chat.service.workflow.answers import AnswerOrchestrator

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio


async def staged_answer(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> tuple[AnswerOrchestrator, Types.GenerateAnswerCommand, SimpleNamespace, UUID]:
    runtime, command, provider = await setup_answer(db)
    original = runtime._complete_staged
    monkeypatch.setattr(
        runtime,
        "_complete_staged",
        AsyncMock(side_effect=Types.AnswerStorageError("injected completion failure")),
    )
    with pytest.raises(Types.AnswerStorageError):
        await runtime.generate_answer(command)
    monkeypatch.setattr(runtime, "_complete_staged", original)
    async with db.begin():
        run = await db.scalar(
            select(ProductGeneration).execution_options(populate_existing=True)
        )
        assert (
            run.answer_metadata["phase"] == "result_ready" and run.status == "pending"
        )
        await db.execute(
            update(ProductGeneration).values(
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
        generation_id = run.id
    return runtime, command, provider, generation_id


async def test_concurrent_instances_and_same_key_share_one_durable_admission(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, command, provider, generation_id = await staged_answer(db, monkeypatch)
    now = datetime.now(UTC)

    async def claim() -> Types.AnswerRecoveryClaimInfo:
        async with runtime.sessions() as session:
            return await Recovery.claim_answer_recovery(
                session,
                Types.ClaimAnswerRecoveryCommand(
                    generation_id=generation_id,
                    user_id=command.user_id,
                    now=now,
                ),
            )

    claims = await asyncio.wait_for(
        asyncio.gather(*(claim() for _ in range(12))), timeout=15
    )
    assert [item.attempt_count for item in claims].count(1) == 1
    assert sum(item.attempt_count is None for item in claims) == 11
    other = AnswerOrchestrator(
        runtime.sessions, runtime.text, runtime.retriever, pricing=runtime.pricing
    )
    with pytest.raises(Types.AnswerStorageError):
        await other.generate_answer(command)
    async with db.begin():
        assert (
            await db.scalar(select(func.count()).select_from(AnswerRecoveryAttempt))
            == 1
        )
        assert await db.scalar(select(ProductGeneration.answer_recovery_attempts)) == 1
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 0
    provider.generate_text.assert_awaited_once()


async def test_exhausted_budget_then_audited_manual_commit_ack_loss_is_exactly_once(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, command, provider, generation_id = await staged_answer(db, monkeypatch)
    original = runtime._finalize
    monkeypatch.setattr(
        runtime,
        "_finalize",
        AsyncMock(side_effect=TimeoutError("injected unavailable pool")),
    )
    for count in range(1, 6):
        with pytest.raises(Types.AnswerStorageError):
            await runtime.generate_answer(command)
        async with db.begin():
            assert (
                await db.scalar(select(ProductGeneration.answer_recovery_attempts))
                == count
            )
            await db.execute(
                update(ProductGeneration).values(
                    answer_recovery_next_at=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
    assert await runtime.recover_answers() == 0

    async def lost_ack(*args: object, **kwargs: object) -> Types.AnswerInfo:
        await original(generation_id, command.user_id, recover=True)
        raise RuntimeError("injected lost finalization acknowledgement")

    monkeypatch.setattr(runtime, "_finalize", lost_ack)
    manual = Types.ClaimAnswerRecoveryCommand(
        generation_id=generation_id,
        user_id=command.user_id,
        now=datetime.now(UTC),
        operator="ops-456",
        reason="Database connectivity restored; durable result and reservation verified.",
    )
    answer = await runtime.recover_answer(manual)
    assert answer.status == "succeeded"
    assert await runtime.generate_answer(command) == answer
    assert await runtime.recover_answer(manual) == answer
    async with db.begin():
        run = await db.scalar(
            select(ProductGeneration).execution_options(populate_existing=True)
        )
        attempts = list(
            await db.scalars(
                select(AnswerRecoveryAttempt).order_by(
                    AnswerRecoveryAttempt.attempt_count
                )
            )
        )
        assert (
            run.answer_recovery_attempts == 6
            and run.answer_recovery_quarantined_at is not None
        )
        assert len(attempts) == 6
        assert all(
            attempt.failure_class == "storage_unavailable" for attempt in attempts[:5]
        )
        assert (
            attempts[-1].operator == manual.operator
            and attempts[-1].reason == manual.reason
        )
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 1
        )
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1
    provider.generate_text.assert_awaited_once()


def migrate(connection: Connection, direction: str) -> None:
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "apps/api/alembic.ini")))
    revision = scripts.get_revision("0036")
    with Operations.context(MigrationContext.configure(connection)):
        getattr(revision.module, direction)()


@pytest.mark.parametrize("path", ["alembic", "init"])
async def test_migration_preserves_legacy_facts_and_refuses_erasing_budget(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    runtime, command, _, generation_id = await staged_answer(db, monkeypatch)
    async with db.begin():
        before = (
            await db.execute(
                text(
                    "SELECT id, status, answer_metadata, answer_lease_until FROM product_generations"
                )
            )
        ).all()
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
        if path == "alembic":
            await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        else:
            sql = (
                ROOT / "infra/postgres/init/026_answer_recovery_policy.sql"
            ).read_text(encoding="utf-8")
            assert sql == (
                ROOT / "apps/api/alembic/sql/0036_answer_recovery_policy.sql"
            ).read_text(encoding="utf-8")
            await db.execute(text(sql))
        assert (
            await db.execute(
                text(
                    "SELECT id, status, answer_metadata, answer_lease_until FROM product_generations"
                )
            )
        ).all() == before
        assert await db.scalar(select(ProductGeneration.answer_recovery_attempts)) == 0
    async with runtime.sessions() as session:
        await Recovery.claim_answer_recovery(
            session,
            Types.ClaimAnswerRecoveryCommand(
                generation_id=generation_id,
                user_id=command.user_id,
                now=datetime.now(UTC),
            ),
        )
    with pytest.raises(DBAPIError, match="Preserve answer recovery history"):
        async with db.begin():
            connection = await db.connection()
            await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
    async with db.begin():
        assert await db.scalar(select(ProductGeneration.answer_recovery_attempts)) == 1
        assert (
            await db.scalar(select(func.count()).select_from(AnswerRecoveryAttempt))
            == 1
        )
