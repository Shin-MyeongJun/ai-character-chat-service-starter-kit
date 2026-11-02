"""U05: migration/init triggers cover mutations and share transaction rollback."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from test_nonstream_answers import setup_answer

from app.db.models.chat import Conversation, Message
from app.db.models.character import Character
from app.db.models.message_history import ChatHistoryVersion
from app.db.models.product_usage import ProductGeneration

ROOT = Path(__file__).resolve().parents[3]
pytestmark = pytest.mark.asyncio


def migrate(connection, direction):
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "apps/api/alembic.ini")))
    revision = scripts.get_revision("0033")
    with Operations.context(MigrationContext.configure(connection)):
        getattr(revision.module, direction)()


async def version(db, cid):
    return await db.scalar(select(ChatHistoryVersion.version).where(ChatHistoryVersion.conversation_id == cid))


async def test_migration_preserves_messages_and_installs_legacy_change_detection(db):
    _, command, _ = await setup_answer(db)
    async with db.begin():
        before = (await db.execute(text("SELECT * FROM messages"))).all()
        connection = await db.connection()
        await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
        await connection.run_sync(lambda conn: migrate(conn, "upgrade"))
        assert (await db.execute(text("SELECT * FROM messages"))).all() == before
        assert await version(db, command.conversation_id) == 0
        await db.execute(delete(Message).where(Message.id == command.input_message_id))
        assert await version(db, command.conversation_id) == 1
        # Reinstalling init SQL must preserve the counter and existing data.
        sql = (ROOT / "infra/postgres/init/023_chat_history_versions.sql").read_text(encoding="utf-8")
        assert sql == (ROOT / "apps/api/alembic/sql/0033_chat_history_versions.sql").read_text(encoding="utf-8")
        await db.execute(text(sql))
        assert await version(db, command.conversation_id) == 1


async def test_insert_update_delete_and_rollback_advance_only_committed_version(db):
    _, command, _ = await setup_answer(db)
    async with db.begin():
        before = await version(db, command.conversation_id)
    with pytest.raises(RuntimeError, match="rollback"):
        async with db.begin():
            await db.execute(update(Message).values(content="uncommitted"))
            assert await version(db, command.conversation_id) == before + 1
            raise RuntimeError("rollback")
    async with db.begin():
        assert await version(db, command.conversation_id) == before
        await db.execute(update(Message).values(content="committed"))
        assert await version(db, command.conversation_id) == before + 1
        added = await db.scalar(insert(Message).values(
            conversation_id=command.conversation_id, sender_type="system", content="added"
        ).returning(Message.id))
        assert await version(db, command.conversation_id) == before + 2
        await db.execute(delete(Message).where(Message.id == added))
        assert await version(db, command.conversation_id) == before + 3
        # Parent cascade deletes must neither resurrect stamps nor fail their FK.
        await db.execute(delete(Conversation).where(Conversation.id == command.conversation_id))
        assert await version(db, command.conversation_id) is None


async def test_foreign_key_nulling_invalidates_old_message_metadata(db):
    _, command, _ = await setup_answer(db)
    async with db.begin():
        character = Character(owner_id=command.user_id, name="unpublished", persona_prompt="unused")
        db.add(character)
        await db.flush()
        await db.execute(update(Message).values(character_id=character.id))
        before = await version(db, command.conversation_id)
        await db.execute(delete(Character).where(Character.id == character.id))
        assert await version(db, command.conversation_id) == before + 1
        assert await db.scalar(select(Message.character_id)) is None


async def test_downgrade_refuses_pending_answer(db):
    orchestrator, command, _ = await setup_answer(db)
    answer = await orchestrator.generate_answer(command)
    async with db.begin():
        await db.execute(update(ProductGeneration).where(ProductGeneration.id == answer.generation_id).values(status="pending", finished_at=None))
    with pytest.raises(DBAPIError, match="Drain pending answers"):
        async with db.begin():
            connection = await db.connection()
            await connection.run_sync(lambda conn: migrate(conn, "downgrade"))
    async with db.begin():
        assert await version(db, command.conversation_id) > 0

