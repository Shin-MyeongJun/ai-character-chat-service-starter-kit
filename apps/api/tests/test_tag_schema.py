"""Shared content tag schema, migration preservation and FK behavior."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from app.db.base import Base
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex, CreateTable
from test_media_migrations import migration_sql
from test_product_migrations import signature

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ("product", "character", "lorebook")
LINKS = tuple(
    name for target in TARGETS for name in (f"{target}_tags", f"{target}_internal_tags")
)
TABLES = ("tags", *LINKS)
requires_postgres = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL required for PostgreSQL integration tests",
)


def test_current_tag_ddl_matches_models_and_new_migration_tables():
    initial = (ROOT / "infra/postgres/init/019_tags.sql").read_text(encoding="utf-8")
    migration = (ROOT / "apps/api/alembic/sql/0029_content_tags.sql").read_text(
        encoding="utf-8"
    )
    dialect = postgresql.dialect()
    for name in TABLES:
        table = Base.metadata.tables[name]
        statements = [str(CreateTable(table).compile(dialect=dialect)).strip() + ";"]
        statements += [
            str(CreateIndex(index).compile(dialect=dialect)).strip() + ";"
            for index in table.indexes
        ]
        for statement in statements:
            assert statement in initial
            if name.startswith(("character_", "lorebook_")):
                assert statement in migration


def test_tag_dictionary_and_connections_have_required_boundaries():
    assert "kind" not in Base.metadata.tables["tags"].c
    assert "normalized_name" not in Base.metadata.tables["tags"].c
    for target in TARGETS:
        for suffix in ("tags", "internal_tags"):
            table = Base.metadata.tables[f"{target}_{suffix}"]
            assert {column.name for column in table.primary_key} == {
                f"{target}_id",
                "tag_id",
            }
            assert "tag_kind" not in table.c
            endpoints = {
                (fk.parent.name, fk.target_fullname, fk.ondelete)
                for fk in table.foreign_keys
            }
            assert endpoints == {
                (f"{target}_id", f"{target}s.id", "CASCADE"),
                ("tag_id", "tags.id", "RESTRICT"),
                ("assigned_by", "users.id", "SET NULL"),
            }
            assert ("source" in table.c) == (suffix == "internal_tags")
            assert ("sort_order" in table.c) == (suffix == "tags")
    assert not any(
        name in Base.metadata.tables
        for name in (
            "author_tags",
            "reader_tags",
            "event_tags",
            "user_tags",
            "product_snapshot_tags",
        )
    )


def test_tag_offline_migration_chain_and_guards():
    def render(direction, revisions):
        return subprocess.check_output(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "apps/api/alembic.ini"),
                direction,
                revisions,
                "--sql",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )

    upgrade = render("upgrade", "head")
    downgrade = render("downgrade", "0029:0028")
    for name in TABLES:
        assert f"CREATE TABLE {name}" in upgrade
    for name in LINKS[2:]:
        assert f"DROP TABLE {name}" in downgrade
    assert "Duplicate tag names across kinds" in upgrade
    assert "Content tag data exists; preserve it before downgrade" in downgrade
    assert "ALTER TABLE tags DROP COLUMN kind" in upgrade
    assert "DROP TABLE products" not in downgrade
    # The existing deployed migration is still the original kind-based schema.
    historical = (ROOT / "apps/api/alembic/sql/0028_tags.sql").read_text(
        encoding="utf-8"
    )
    assert "uq_tags_kind_name UNIQUE (kind, name)" in historical


async def seed_target(db, target):
    owner_id, target_id = uuid4(), uuid4()
    await db.execute(
        text("INSERT INTO users(id,email) VALUES (:id,'tags@example.test')"),
        {"id": owner_id},
    )
    label = "name" if target == "character" else "title"
    extra_columns = ",persona_prompt" if target == "character" else ""
    extra_values = ",'Test persona'" if target == "character" else ""
    await db.execute(
        text(
            f"INSERT INTO {target}s(id,owner_id,{label}{extra_columns}) "
            f"VALUES (:id,:owner,'Tagged content'{extra_values})"
        ),
        {"id": target_id, "owner": owner_id},
    )
    return target_id


@requires_postgres
@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.asyncio
async def test_public_internal_reuse_duplicates_limits_and_deletion(db, target):
    target_id = await seed_target(db, target)
    actor_id = uuid4()
    await db.execute(
        text("INSERT INTO users(id,email) VALUES (:id,'tag-actor@example.test')"),
        {"id": actor_id},
    )
    tag_id = await db.scalar(
        text("INSERT INTO tags(name) VALUES ('shared') RETURNING id")
    )
    params = {"target": target_id, "tag": tag_id, "actor": actor_id}
    public = f"{target}_tags"
    internal = f"{target}_internal_tags"
    await db.execute(
        text(
            f"INSERT INTO {public}({target}_id,tag_id,assigned_by) VALUES (:target,:tag,:actor)"
        ),
        params,
    )
    await db.execute(
        text(
            f"INSERT INTO {internal}({target}_id,tag_id,source,assigned_by) VALUES (:target,:tag,'admin',:actor)"
        ),
        params,
    )
    # Two connections may share one dictionary ID; each connection is unique.
    for table in (public, internal):
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(text(f"INSERT INTO {table} SELECT * FROM {table}"))
    for invalid in ("", "   ", "shared"):
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text("INSERT INTO tags(name) VALUES (:name)"), {"name": invalid}
                )
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text(f"UPDATE {internal} SET source='author'"))
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text("DELETE FROM tags WHERE id=:tag"), params)
    for table in (public, internal):
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(f"UPDATE {table} SET tag_id=:missing"), {"missing": uuid4()}
                )
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(
                    text(f"UPDATE {table} SET {target}_id=:missing"),
                    {"missing": uuid4()},
                )
    # No case folding, whitespace folding or tag count cap.
    for name in ("Fantasy", "fantasy", "현대판타지", "현대 판타지"):
        await db.execute(text("INSERT INTO tags(name) VALUES (:name)"), {"name": name})
    await db.execute(
        text(
            "INSERT INTO tags(name) SELECT 'tag-' || n FROM generate_series(1,100) AS n"
        )
    )
    for table in (public, internal):
        columns = f"{target}_id,tag_id" + (",source" if table == internal else "")
        values = ":target,id" + (",'system'" if table == internal else "")
        await db.execute(
            text(
                f"INSERT INTO {table}({columns}) SELECT {values} FROM tags WHERE id<>:tag"
            ),
            params,
        )
        assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 105
    assert await db.scalar(text(f"SELECT bool_and(sort_order=0) FROM {public}"))
    await db.execute(text("UPDATE tags SET is_active=false"))
    await db.execute(text("DELETE FROM users WHERE id=:actor"), params)
    for table in (public, internal):
        assert (
            await db.scalar(
                text(f"SELECT count(*) FROM {table} WHERE assigned_by IS NOT NULL")
            )
            == 0
        )
        assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 105
    await db.execute(text(f"DELETE FROM {target}s WHERE id=:target"), params)
    for table in (public, internal):
        assert await db.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    assert await db.scalar(text("SELECT count(*) FROM tags")) == 105


@requires_postgres
@pytest.mark.asyncio
async def test_tag_migration_preserves_legacy_connections_and_guards_conflicts(db):
    upgrade = await migration_sql("upgrade", "0028:0029")
    downgrade = await migration_sql("downgrade", "0029:0028")
    async with db.bind.connect() as conn:
        schema = await conn.scalar(text("SELECT current_schema()"))
        expected = await conn.run_sync(signature, schema)
    raw = await db.bind.raw_connection()
    connection = raw.driver_connection
    try:
        for name in reversed(TABLES):
            await connection.execute(f"DROP TABLE {name}")
        await connection.execute(
            (ROOT / "apps/api/alembic/sql/0028_tags.sql").read_text(encoding="utf-8")
        )
        await connection.execute(
            "CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('0028')"
        )
        async with db.bind.connect() as conn:
            legacy_schema = await conn.run_sync(signature, schema)
        owner, product, public, internal = (uuid4() for _ in range(4))
        await connection.execute(
            "INSERT INTO users(id,email) VALUES($1,'tag-legacy@example.test')", owner
        )
        await connection.execute(
            "INSERT INTO products(id,owner_id,title) VALUES($1,$2,'Legacy')",
            product,
            owner,
        )
        await connection.execute(
            "INSERT INTO tags(id,kind,name,description) VALUES($1,'public','legacy','public metadata'),($2,'internal','legacy','internal metadata')",
            public,
            internal,
        )
        await connection.execute(
            "INSERT INTO product_tags(product_id,tag_id,sort_order) VALUES($1,$2,7)",
            product,
            public,
        )
        await connection.execute(
            "INSERT INTO product_internal_tags(product_id,tag_id,source,assigned_by) VALUES($1,$2,'admin',$3)",
            product,
            internal,
            owner,
        )
        with pytest.raises(
            asyncpg.RaiseError, match="Duplicate tag names across kinds"
        ):
            await connection.execute(upgrade)
        await connection.execute("ROLLBACK")
        assert await connection.fetchval("SELECT count(*) FROM tags") == 2
        assert (
            await connection.fetchval("SELECT kind FROM tags WHERE id=$1", internal)
            == "internal"
        )
        await connection.execute(
            "UPDATE tags SET name='legacy-interest' WHERE id=$1", internal
        )
        await connection.execute(upgrade)
        async with db.bind.connect() as conn:
            assert await conn.run_sync(signature, schema) == expected
        assert (
            await connection.fetchval(
                "SELECT sort_order FROM product_tags WHERE tag_id=$1", public
            )
            == 7
        )
        assert (
            await connection.fetchval(
                "SELECT assigned_by FROM product_internal_tags WHERE tag_id=$1",
                internal,
            )
            == owner
        )
        assert (
            await connection.fetchval(
                "SELECT description FROM tags WHERE id=$1", internal
            )
            == "internal metadata"
        )
        # The same formerly public tag can now be an internal classification.
        await connection.execute(
            "INSERT INTO product_internal_tags(product_id,tag_id,source) VALUES($1,$2,'system')",
            product,
            public,
        )
        with pytest.raises(asyncpg.RaiseError, match="preserve it before downgrade"):
            await connection.execute(downgrade)
        await connection.execute("ROLLBACK")
        assert await connection.fetchval("SELECT count(*) FROM tags") == 2
        await connection.execute(
            "DELETE FROM product_tags; DELETE FROM product_internal_tags; DELETE FROM tags"
        )
        await connection.execute(downgrade)
        async with db.bind.connect() as conn:
            assert await conn.run_sync(signature, schema) == legacy_schema
        assert (
            await connection.fetchval("SELECT title FROM products WHERE id=$1", product)
            == "Legacy"
        )
    finally:
        await connection.execute("ROLLBACK")
        raw.close()
