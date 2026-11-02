"""U17: recovery eligibility, generic plans and non-destructive index migration."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import (
    Connection,
    ExecutionContext,
    event,
    insert,
    literal,
    select,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from test_nonstream_answers import setup_answer
from test_product_usage import scenario

from app.db.models.product_usage import ProductGeneration
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import answers as Command
from app.modules.chatting.chat.service.command import generation as GenerationCommand

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio
OLD_INDEX = "ix_product_generations_answer_lease_until"
NEW_INDEX = "ix_generation_pending_answer_lease"


async def seed_answers(
    db: AsyncSession,
) -> tuple[datetime, list[UUID], Types.AnswerInfo]:
    orchestrator, command, _ = await setup_answer(db)
    answer = await orchestrator.generate_answer(command)
    now = datetime(2026, 11, 2, tzinfo=UTC)
    due_ids: list[UUID] = []
    async with db.begin():
        original = dict(
            (await db.execute(select(ProductGeneration.__table__))).mappings().one()
        )
        assert original["answer_lease_until"] is None
        for name, status, lease in (
            ("old", "pending", now - timedelta(hours=1)),
            ("recent", "pending", now - timedelta(seconds=1)),
            ("boundary", "pending", now),
            ("live", "pending", now + timedelta(seconds=1)),
            ("legacy", "pending", None),
            *(
                (status, status, now - timedelta(days=1))
                for status in ("succeeded", "failed", "cancelled", "stale")
            ),
        ):
            generation_id = uuid4()
            await db.execute(
                insert(ProductGeneration).values(
                    {
                        **original,
                        "id": generation_id,
                        "request_key": name,
                        "status": status,
                        "answer_lease_until": lease,
                    }
                )
            )
            if name in {"old", "recent", "boundary"}:
                due_ids.append(generation_id)
    return now, due_ids, answer


async def test_scan_keeps_expiry_boundary_order_limit_and_excludes_terminal_legacy_live(
    db: AsyncSession,
) -> None:
    now, due_ids, _ = await seed_answers(db)
    async with db.begin():
        page = await Command.list_expired_answers(
            db, Types.ListExpiredAnswersCommand(now=now, limit=2)
        )
        assert [item.id for item in page] == due_ids[:2]
        all_due = await Command.list_expired_answers(
            db, Types.ListExpiredAnswersCommand(now=now, limit=100)
        )
        assert [item.id for item in all_due] == due_ids
        assert all(item.status == "pending" for item in all_due)


async def index_definitions(db: AsyncSession) -> dict[str, str]:
    return dict(
        (
            await db.execute(
                text("""
        SELECT indexname, indexdef FROM pg_indexes
        WHERE schemaname = current_schema() AND tablename = 'product_generations'
    """)
            )
        ).all()
    )


def migrate(connection: Connection, direction: str) -> None:
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "apps/api/alembic.ini")))
    revision = scripts.get_revision("0035")
    with Operations.context(MigrationContext.configure(connection)):
        getattr(revision.module, direction)()


@pytest.mark.parametrize("path", ["alembic", "init"])
async def test_index_upgrade_downgrade_preserves_all_generation_facts(
    db: AsyncSession, path: str
) -> None:
    await seed_answers(db)
    async with db.begin():
        before = (
            await db.execute(text("SELECT * FROM product_generations ORDER BY id"))
        ).all()
        expected = await index_definitions(db)
        assert NEW_INDEX in expected and OLD_INDEX not in expected
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
        downgraded = await index_definitions(db)
        assert OLD_INDEX in downgraded and NEW_INDEX not in downgraded
        if path == "alembic":
            await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        else:
            sql = (
                ROOT / "infra/postgres/init/025_pending_answer_recovery.sql"
            ).read_text(encoding="utf-8")
            for statement in sql.split(";"):
                if statement.strip():
                    await db.execute(text(statement))
        assert await index_definitions(db) == expected
        assert (
            await db.execute(text("SELECT * FROM product_generations ORDER BY id"))
        ).all() == before


async def test_prepared_generic_recovery_uses_pending_index_with_terminal_history(
    db: AsyncSession,
) -> None:
    now, due_ids, answer = await seed_answers(db)
    async with db.begin():
        # Real row width/metadata and valid FK parents; history dominates the
        # table while expired pending answers remain a small work queue.
        columns = list(ProductGeneration.__table__.columns)
        names = ", ".join(column.name for column in columns)
        values = ", ".join(
            "gen_random_uuid()"
            if column.name == "id"
            else "'history-' || i"
            if column.name == "request_key"
            else "'succeeded'"
            if column.name == "status"
            else "TIMESTAMPTZ '2020-01-01'"
            if column.name == "answer_lease_until"
            else "g." + column.name
            for column in columns
        )
        await db.execute(
            text(
                f"INSERT INTO product_generations ({names}) SELECT {values} "
                "FROM product_generations g CROSS JOIN generate_series(1, 20000) i "
                "WHERE g.id = :id"
            ),
            {"id": answer.generation_id},
        )
        await db.execute(text("ANALYZE product_generations"))
        captured: list[tuple[str, tuple[object, ...]]] = []

        def capture(
            conn: Connection,
            cursor: object,
            statement: str,
            parameters: tuple[object, ...],
            context: ExecutionContext,
            executemany: bool,
        ) -> None:
            captured.append((statement, parameters))

        connection = await db.connection()
        event.listen(connection.sync_connection, "before_cursor_execute", capture)
        try:
            found = await Command.list_expired_answers(
                db, Types.ListExpiredAnswersCommand(now=now, limit=100)
            )
        finally:
            event.remove(connection.sync_connection, "before_cursor_execute", capture)
        assert [item.id for item in found] == due_ids
        sql, parameters = captured[0]
        arguments = ", ".join(
            str(
                literal(value).compile(
                    dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
                )
            )
            for value in parameters
        )
        driver = (await connection.get_raw_connection()).driver_connection
        await driver.execute("SET LOCAL plan_cache_mode = force_generic_plan")
        await driver.execute(f"PREPARE u17_recovery_test AS {sql}")
        try:
            raw = await driver.fetchval(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                f"EXECUTE u17_recovery_test({arguments})"
            )
        finally:
            await driver.execute("DEALLOCATE u17_recovery_test")
        plan = (json.loads(raw) if isinstance(raw, str) else raw)[0]["Plan"]
        assert plan["Actual Rows"] == len(due_ids)
        assert plan["Plans"][0]["Index Name"] == NEW_INDEX
        assert plan["Plans"][0].get("Rows Removed by Filter", 0) == 0


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled", "stale"])
async def test_terminal_lease_clear_is_atomic_and_replay_keeps_metadata(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    outcome: Literal["succeeded", "failed", "cancelled", "stale"],
) -> None:
    owner, _, _, conversation_id, character_id = await scenario(db)
    run = await GenerationCommand.begin_generation(
        db,
        Types.BeginGenerationCommand(
            conversation_id=conversation_id,
            user_id=owner.id,
            request_key="leased",
            input_text="input",
        ),
    )
    lease = datetime.now(UTC) + timedelta(hours=1)
    metadata: Types.AnswerMetadata = {"phase": "result_ready", "content": "output"}
    await Command.update_answer(
        db,
        Types.UpdateAnswerCommand(
            generation_id=run.id,
            user_id=owner.id,
            metadata=metadata,
            lease_until=lease,
        ),
    )
    if outcome == "stale":
        monkeypatch.setattr(
            GenerationCommand,
            "ensure_available",
            AsyncMock(side_effect=ValueError("Version expired.")),
        )
    command = Types.FinishGenerationCommand(
        generation_id=run.id,
        user_id=owner.id,
        value=Types.GenerationResult(
            1,
            1,
            0,
            (Types.GeneratedMessage(character_id, "output"),)
            if outcome in {"succeeded", "stale"}
            else (),
            outcome="succeeded" if outcome == "stale" else outcome,
        ),
    )
    with pytest.raises(RuntimeError, match="outer rollback"):
        async with use_case_transaction(db):
            result = await GenerationCommand.finish_generation(db, command)
            assert result.status == outcome
            assert await db.scalar(select(ProductGeneration.answer_lease_until)) is None
            raise RuntimeError("outer rollback")
    async with db.begin():
        state = (await db.execute(select(ProductGeneration))).scalar_one()
        assert state.status == "pending" and state.answer_lease_until == lease
        assert state.answer_metadata == metadata and state.finished_at is None
    result = await GenerationCommand.finish_generation(db, command)
    assert result.status == outcome
    async with db.begin():
        state = (await db.execute(select(ProductGeneration))).scalar_one()
        assert state.answer_lease_until is None
        assert state.answer_metadata == metadata and state.finished_at is not None
    assert await GenerationCommand.finish_generation(db, command) == result
