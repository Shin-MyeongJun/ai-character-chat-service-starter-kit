"""U01 migration preserves legacy jobs and refuses to discard active targets."""

from pathlib import Path
from typing import Literal

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_memory_claim_fencing import claim, seed_conversation

from app.db.transaction import use_case_transaction
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as Types

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio


def migrate(connection: Connection, direction: Literal["upgrade", "downgrade"]) -> None:
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "apps/api/alembic.ini")))
    revision = scripts.get_revision("0032")
    assert revision is not None
    with Operations.context(MigrationContext.configure(connection)):
        if direction == "upgrade":
            revision.module.upgrade()
        else:
            revision.module.downgrade()


async def test_migration_and_fresh_init_preserve_legacy_queue(db: AsyncSession) -> None:
    cid, _ = await seed_conversation(db)
    async with use_case_transaction(db):
        before = (
            await db.execute(
                text("SELECT requested_generation, status, owner_id FROM memory_jobs")
            )
        ).one()
        await db.execute(
            text("ALTER TABLE memory_jobs DROP COLUMN summary_through_position")
        )
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        assert (
            await db.execute(
                text("SELECT requested_generation, status, owner_id FROM memory_jobs")
            )
        ).one() == before
        assert (
            await db.scalar(text("SELECT summary_through_position FROM memory_jobs"))
            is None
        )
    current = await claim(db)
    assert current.conversation_id == cid and current.summary_through_position is None
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=current)
    )
    async with use_case_transaction(db):
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
        sql = (ROOT / "infra/postgres/init/022_memory_summary_target.sql").read_text(
            encoding="utf-8"
        )
        await db.execute(text(sql))
        await db.execute(text(sql))
        column = (
            await db.execute(
                text(
                    "SELECT data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'memory_jobs' AND column_name = 'summary_through_position'"
                )
            )
        ).one()
        assert tuple(column) == ("bigint", "YES", None)
    with pytest.raises(DBAPIError):
        async with use_case_transaction(db):
            await db.execute(
                text("UPDATE memory_jobs SET summary_through_position = 0")
            )


@pytest.mark.parametrize("running", [False, True])
async def test_downgrade_refuses_unfinished_compaction(
    db: AsyncSession, running: bool
) -> None:
    cid, owner_id = await seed_conversation(db)
    await MemoryService.schedule_memory_work(
        db,
        Types.ScheduleMemoryWorkCommand(
            conversation_id=cid, owner_id=owner_id, summary_through_position=10
        ),
    )
    if running:
        await claim(db)
    with pytest.raises(DBAPIError, match="Drain memory compaction requests"):
        async with use_case_transaction(db):
            connection = await db.connection()
            await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
    async with use_case_transaction(db):
        assert (
            await db.scalar(text("SELECT summary_through_position FROM memory_jobs"))
            == 10
        )
