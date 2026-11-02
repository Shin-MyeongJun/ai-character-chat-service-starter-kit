"""0034/init/ORM schema parity and rollback protection on actual PostgreSQL."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from test_identity_auth import identity_db as identity_db_fixture
from test_media_migrations import migration_sql
from test_product_migrations import signature

ROOT = Path(__file__).resolve().parents[3]
identity_db = identity_db_fixture


def test_mail_migration_and_initial_schema_share_ddl():
    assert (ROOT / "apps/api/alembic/sql/0034_auth_mail_outbox.sql").read_bytes() == (
        ROOT / "infra/postgres/init/024_auth_mail_outbox.sql"
    ).read_bytes()


@pytest.mark.asyncio
async def test_pg_mail_online_upgrade_runs_through_asyncpg(identity_db):
    # Exercise Alembic's SQLAlchemy execution path, not only --sql + raw execute.
    path = ROOT / "apps/api/alembic/versions/0034_auth_mail_outbox.py"
    spec = importlib.util.spec_from_file_location("mail_outbox_migration", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = identity_db.kw["bind"]

    def upgrade(connection):
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE auth_mail_outbox"))
        await conn.run_sync(upgrade)
        assert await conn.scalar(text("SELECT count(*) FROM auth_mail_outbox")) == 0


@pytest.mark.asyncio
async def test_pg_mail_migration_preserves_proofs_and_guards_pending_downgrade(
    identity_db,
):
    engine = identity_db.kw["bind"]
    upgrade = await migration_sql("upgrade", "0033:0034")
    downgrade = await migration_sql("downgrade", "0034:0033")
    async with engine.connect() as conn:
        schema = await conn.scalar(text("SELECT current_schema()"))
        expected = (await conn.run_sync(signature, schema))["auth_mail_outbox"]
    raw = await engine.raw_connection()
    connection = raw.driver_connection
    try:
        await connection.execute("DROP TABLE auth_mail_outbox")
        await connection.execute(
            "CREATE TABLE alembic_version(version_num VARCHAR(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('0033')"
        )
        user_id = uuid4()
        await connection.execute(
            "INSERT INTO users(id,email) VALUES($1,'migration@example.com')", user_id
        )
        await connection.execute(
            "INSERT INTO auth_action_tokens(user_id,token_hash,purpose,expires_at) VALUES($1,'legacy-proof-hash','verify',now() + interval '30 minutes')",
            user_id,
        )
        await connection.execute(upgrade)
        assert await connection.fetchval("SELECT count(*) FROM auth_action_tokens") == 1
        assert await connection.fetchval("SELECT count(*) FROM auth_mail_outbox") == 0
        async with engine.connect() as conn:
            assert (await conn.run_sync(signature, schema))[
                "auth_mail_outbox"
            ] == expected
            constraints = await conn.run_sync(
                lambda sync: inspect(sync).get_check_constraints(
                    "auth_mail_outbox", schema=schema
                )
            )
            assert {item["name"] for item in constraints} == {
                "ck_auth_mail_status",
                "ck_auth_mail_attempt_count",
                "ck_auth_mail_claim",
                "ck_auth_mail_payload",
            }
        await connection.execute(
            "INSERT INTO auth_mail_outbox(token_hash,encrypted_token,created_at,available_at) VALUES ('legacy-proof-hash','ciphertext',now(),now())"
        )
        for status in ("pending", "processing"):
            if status == "processing":
                await connection.execute(
                    "UPDATE auth_mail_outbox SET status='processing',claim_token=gen_random_uuid(),lease_until=now()+interval '120 seconds'"
                )
            with pytest.raises(Exception, match="Drain authentication mail"):
                await connection.execute(downgrade)
            await connection.execute("ROLLBACK")
            assert (
                await connection.fetchval("SELECT version_num FROM alembic_version")
                == "0034"
            )
        await connection.execute(
            "UPDATE auth_mail_outbox SET status='sent',encrypted_token=NULL,claim_token=NULL,lease_until=NULL"
        )
        await connection.execute(downgrade)
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "0033"
        )
        assert await connection.fetchval("SELECT count(*) FROM auth_action_tokens") == 1
        assert await connection.fetchval("SELECT count(*) FROM users") == 1
    finally:
        raw.close()
