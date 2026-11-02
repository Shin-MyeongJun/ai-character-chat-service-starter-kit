"""U03 migration parity and legacy queue preservation in fixture-owned schemas."""

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
from test_memory_claim_fencing import claim, expire, seed_conversation

from app.db.transaction import use_case_transaction
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as Types

ROOT = Path(__file__).resolve().parents[3]


def migrate(connection: Connection, direction: Literal["upgrade", "downgrade"]) -> None:
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("0031")
    assert revision is not None
    with Operations.context(MigrationContext.configure(connection)):
        if direction == "upgrade":
            revision.module.upgrade()
        else:
            revision.module.downgrade()


@pytest.mark.asyncio
async def test_upgrade_preserves_legacy_jobs_and_reclaim_assigns_token(
    db: AsyncSession,
) -> None:
    conversation_id, _ = await seed_conversation(db)
    await claim(db)
    async with use_case_transaction(db):
        await db.execute(text("ALTER TABLE memory_jobs DROP COLUMN claim_token"))
        before = (await db.execute(text("SELECT * FROM memory_jobs"))).all()
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        after = (await db.execute(text("SELECT * FROM memory_jobs"))).all()
        assert tuple(after[0])[:-1] == tuple(before[0])
        assert after[0][-1] is None
    await expire(db, conversation_id)
    current = await claim(db)
    assert current.claim_token is not None
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=current)
    )
    async with use_case_transaction(db):
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
        # Fresh-install SQL must produce the same nullable UUID as Alembic/ORM.
        await db.execute(
            text(
                (ROOT / "infra/postgres/init/021_memory_claim_token.sql").read_text(
                    encoding="utf-8"
                )
            )
        )
        await db.execute(
            text(
                (ROOT / "infra/postgres/init/021_memory_claim_token.sql").read_text(
                    encoding="utf-8"
                )
            )
        )
        column = (
            await db.execute(
                text(
                    "SELECT data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'memory_jobs' AND column_name = 'claim_token'"
                )
            )
        ).one()
        assert tuple(column) == ("uuid", "YES", None)
        assert (
            await db.scalar(text("SELECT completed_generation FROM memory_jobs")) == 1
        )


@pytest.mark.asyncio
async def test_downgrade_refuses_running_claim_without_losing_data(
    db: AsyncSession,
) -> None:
    await seed_conversation(db)
    current = await claim(db)
    with pytest.raises(DBAPIError, match="Stop and drain memory workers"):
        async with use_case_transaction(db):
            connection = await db.connection()
            await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
    async with use_case_transaction(db):
        assert (
            await db.scalar(text("SELECT claim_token FROM memory_jobs"))
            == current.claim_token
        )
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=current)
    )
