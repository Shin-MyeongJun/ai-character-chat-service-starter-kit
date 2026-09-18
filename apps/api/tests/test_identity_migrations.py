"""0020 실제 PostgreSQL 업그레이드·충돌 중단·기존 식별정보 보존을 검증한다."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from test_identity_auth import identity_db  # noqa: F401
from test_media_migrations import migration_sql
from test_product_migrations import signature

ROOT = Path(__file__).resolve().parents[3]
LEGACY_SQL = """
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT UNIQUE NOT NULL,
    password_hash TEXT, display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user', status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_users_role CHECK(role IN ('user','admin')),
    CONSTRAINT ck_users_status CHECK(status IN ('active','suspended','banned'))
);
CREATE TABLE user_oauth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, provider_user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_oauth_provider_user UNIQUE(provider,provider_user_id)
);
CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY);
INSERT INTO alembic_version VALUES ('0019');
"""


@pytest.mark.asyncio
async def test_auth_migration_matches_orm_and_preserves_legacy(identity_db):  # noqa: F811
    engine = identity_db.kw["bind"]
    upgrade = await migration_sql("upgrade", "0019:0020")
    down = await migration_sql("downgrade", "0020:0019")
    sql = (ROOT / "apps/api/alembic/sql/0020_identity.sql").read_text(encoding="utf-8")
    assert sql == (ROOT / "infra/postgres/init/011_identity.sql").read_text(
        encoding="utf-8"
    )
    async with engine.connect() as conn:
        original_schema = await conn.scalar(text("SELECT current_schema()"))
        expected = await conn.run_sync(signature, original_schema)
    schema = "auth_migration_" + uuid4().hex
    raw = await engine.raw_connection()
    connection = raw.driver_connection
    try:
        await connection.execute(f"CREATE SCHEMA {schema}")
        await connection.execute(f"SET search_path TO {schema},public")
        await connection.execute(LEGACY_SQL)
        uid = uuid4()
        await connection.execute(
            "INSERT INTO users(id,email,password_hash,display_name) VALUES($1,' Legacy@Example.com ','legacy-hash','legacy-display')",
            uid,
        )
        await connection.execute(upgrade)
        user = await connection.fetchrow("SELECT * FROM users WHERE id=$1", uid)
        assert user["email"] == "legacy@example.com"
        assert (
            user["password_hash"] == "legacy-hash"
            and user["display_name"] == "legacy-display"
        )
        assert user["email_verified"] is False and user["pending_expires_at"] is None
        async with engine.connect() as conn:
            assert await conn.run_sync(signature, schema) == expected
        await connection.execute("UPDATE users SET email_verified=true")
        with pytest.raises(Exception, match="Authentication data exists"):
            await connection.execute(down)
        await connection.execute("ROLLBACK")
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "0020"
        )
    finally:
        await connection.execute(f"SET search_path TO {original_schema},public")
        await connection.execute(f"DROP SCHEMA {schema} CASCADE")
        raw.close()


@pytest.mark.asyncio
async def test_auth_migration_rejects_normalized_email_collision(identity_db):  # noqa: F811
    engine = identity_db.kw["bind"]
    sql = await migration_sql("upgrade", "0019:0020")
    schema = "auth_collision_" + uuid4().hex
    raw = await engine.raw_connection()
    connection = raw.driver_connection
    original_schema = await connection.fetchval("SELECT current_schema()")
    try:
        await connection.execute(f"CREATE SCHEMA {schema}")
        await connection.execute(f"SET search_path TO {schema},public")
        await connection.execute(LEGACY_SQL)
        await connection.execute(
            "INSERT INTO users(email) VALUES('Duplicate@example.com'),('duplicate@example.com')"
        )
        with pytest.raises(Exception, match="Normalized email collision"):
            await connection.execute(sql)
        await connection.execute("ROLLBACK")
        assert await connection.fetchval("SELECT count(*) FROM users") == 2
        assert (
            await connection.fetchval("SELECT version_num FROM alembic_version")
            == "0019"
        )
    finally:
        await connection.execute(f"SET search_path TO {original_schema},public")
        await connection.execute(f"DROP SCHEMA {schema} CASCADE")
        raw.close()
