"""Prompt DDL, exact TEXT format and loss-protecting downgrade; DB checks require PostgreSQL."""

import hashlib
import os
from pathlib import Path

import asyncpg
import pytest
from app.db.base import Base
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from sqlalchemy import text
from sqlalchemy.engine import make_url
from test_media_migrations import migration_sql
from test_nonstream_answers import setup_answer

ROOT = Path(__file__).resolve().parents[3]


def test_prompt_initial_and_migration_ddl_and_orm_boundaries_match():
    ddl = (ROOT / "apps/api/alembic/sql/0030_generation_prompts.sql").read_text(
        encoding="utf-8"
    )
    assert ddl == (ROOT / "infra/postgres/init/020_generation_prompts.sql").read_text(
        encoding="utf-8"
    )
    table = Base.metadata.tables["generation_prompts"]
    assert {column.name for column in table.primary_key} == {"generation_id"}
    assert (
        str(table.c.request_json.type) == "TEXT" and not table.c.request_json.nullable
    )
    assert {(fk.target_fullname, fk.ondelete) for fk in table.foreign_keys} == {
        ("product_generations.id", "CASCADE")
    }
    assert set(table.c.keys()) == {
        "generation_id",
        "request_json",
        "digest",
        "format_version",
        "created_at",
        "provider",
        "max_output_tokens",
    }
    assert "INSERT INTO" not in ddl.upper() and "UPDATE " not in ddl.upper()


@pytest.mark.asyncio
async def test_offline_prompt_migration_chain_and_downgrade_guard():
    upgrade = await migration_sql("upgrade", "0029:head")
    downgrade = await migration_sql("downgrade", "0030:0029")
    assert "CREATE TABLE generation_prompts" in upgrade
    assert "ON DELETE CASCADE" in upgrade
    assert "'0030'" in upgrade
    assert "Prompt records exist; preserve them before downgrade" in downgrade
    assert "DROP TABLE generation_prompts" in downgrade
    assert "DROP TABLE product_generations" not in downgrade


@pytest.mark.asyncio
async def test_real_migration_preserves_exact_text_and_prevents_lossy_downgrade(db):
    _, command, _ = await setup_answer(db)
    run = await ChatService.begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            request_key=command.request_key,
            input_text="선배님, 같이 갈까요?",
            input_message_id=command.input_message_id,
            expected_revision=command.expected_revision,
        ),
    )
    async with db.bind.connect() as conn:
        schema = await conn.scalar(text("SELECT current_schema()"))
    url = make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql")
    connection = await asyncpg.connect(url.render_as_string(hide_password=False))
    try:
        await connection.execute(f"SET search_path TO {schema}, public")
        await connection.execute(
            "CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('0030')"
        )
        await connection.execute(await migration_sql("downgrade", "0030:0029"))
        await connection.execute(await migration_sql("upgrade", "0029:0030"))
        gid = run.id
        raw = ' {"messages":[{"role":"system","content":"개행\\n과 이모지 🌏"}]}\n'
        digest = hashlib.sha256(raw.encode()).hexdigest()
        await connection.execute(
            "INSERT INTO generation_prompts(generation_id,request_json,digest,format_version,provider,max_output_tokens) VALUES ($1,$2,$3,1,'openai',1200)",
            gid,
            raw,
            digest,
        )
        row = await connection.fetchrow(
            "SELECT request_json,digest FROM generation_prompts WHERE generation_id=$1",
            gid,
        )
        assert row["request_json"] == raw and row["digest"] == digest
        with pytest.raises(asyncpg.PostgresError, match="Prompt records exist"):
            await connection.execute(await migration_sql("downgrade", "0030:0029"))
        await connection.execute("ROLLBACK")
        assert await connection.fetchval("SELECT count(*) FROM generation_prompts") == 1
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "0030"
        )
    finally:
        await connection.close()
