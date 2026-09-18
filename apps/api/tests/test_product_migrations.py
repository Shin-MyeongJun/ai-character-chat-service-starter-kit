# ORM 생성·초기 SQL·Alembic 경로의 열/타입/NULL/FK/UNIQUE를 비교하고 기존 대화·메시지 보존을 확인한다.
# CHECK 제약·일반 인덱스·서버 기본값 전체를 비교하는 검사는 아니다.
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def signature(connection, schema):
    inspector = inspect(connection)
    result = {}
    for table in inspector.get_table_names(schema=schema):
        if table == "alembic_version":
            continue
        columns = sorted(
            (c["name"], str(c["type"]), c["nullable"])
            for c in inspector.get_columns(table, schema=schema)
        )
        foreign = sorted(
            (
                tuple(f["constrained_columns"]),
                f["referred_table"],
                tuple(f["referred_columns"]),
                f["options"].get("ondelete", "NO ACTION"),
            )
            for f in inspector.get_foreign_keys(table, schema=schema)
        )
        unique = sorted(
            tuple(u["column_names"])
            for u in inspector.get_unique_constraints(table, schema=schema)
        )
        result[table] = (columns, foreign, unique)
    return result


@pytest.mark.asyncio
async def test_fresh_init_and_alembic_match_models(db):
    """Execute real PostgreSQL DDL in isolated schemas, preserving legacy rows."""
    url = make_url(os.environ["TEST_DATABASE_URL"])
    engine = db.bind
    async with engine.connect() as conn:
        reference_schema = await conn.scalar(text("SELECT current_schema()"))
        expected = await conn.run_sync(signature, reference_schema)
    suffix = uuid4().hex
    names = ["migration_" + suffix, "initial_" + suffix]
    connection = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    try:
        for name in names:
            await connection.execute(f"CREATE SCHEMA {name}")
        # Real legacy baseline, with a row whose version cannot be inferred.
        await connection.execute(f"SET search_path TO {names[0]}, public")
        sql = await asyncio.to_thread(
            subprocess.check_output,
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "apps/api/alembic.ini"),
                "upgrade",
                "0001",
                "--sql",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        await connection.execute(sql)
        uid, pid, cid = uuid4(), uuid4(), uuid4()
        await connection.execute(
            "INSERT INTO users(id,email) VALUES($1,'legacy@test.local')", uid
        )
        await connection.execute(
            "INSERT INTO products(id,owner_id,title) VALUES($1,$2,'Legacy')", pid, uid
        )
        await connection.execute(
            "INSERT INTO conversations(id,user_id,product_id) VALUES($1,$2,$3)",
            cid,
            uid,
            pid,
        )
        # A populated legacy history with tied timestamps must retain a stable
        # deterministic order, and newly generated positions must follow it.
        message_ids = [uuid4() for _ in range(3)]
        for message_id in sorted(message_ids, reverse=True):
            await connection.execute(
                "INSERT INTO messages(id,conversation_id,sender_type,content,created_at) "
                "VALUES($1,$2,'user','Legacy','2026-01-01T00:00:00Z')",
                message_id,
                cid,
            )
        upgrade = await asyncio.to_thread(
            subprocess.check_output,
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "apps/api/alembic.ini"),
                "upgrade",
                "0001:head",
                "--sql",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        await connection.execute(upgrade)
        legacy = await connection.fetchrow(
            "SELECT product_id,product_snapshot_id FROM conversations WHERE id=$1", cid
        )
        assert legacy["product_id"] == pid and legacy["product_snapshot_id"] is None
        ordered = await connection.fetch(
            "SELECT id,position,revision FROM messages WHERE conversation_id=$1 ORDER BY position",
            cid,
        )
        assert [row["id"] for row in ordered] == sorted(message_ids)
        assert [row["revision"] for row in ordered] == [1, 1, 1]
        new_position = await connection.fetchval(
            "INSERT INTO messages(conversation_id,sender_type,content) VALUES($1,'user','New') RETURNING position",
            cid,
        )
        assert new_position > ordered[-1]["position"]
        await connection.execute(f"SET search_path TO {names[1]}, public")
        for path in sorted((ROOT / "infra/postgres/init").glob("*.sql")):
            await connection.execute(path.read_text(encoding="utf-8-sig"))
        async with engine.connect() as conn:
            for name in names:
                actual = await conn.run_sync(signature, name)
                assert actual == expected, {
                    t: (actual.get(t), expected.get(t))
                    for t in actual.keys() | expected.keys()
                    if actual.get(t) != expected.get(t)
                }
    finally:
        await connection.execute("ROLLBACK")
        await connection.execute("SET search_path TO public")
        for name in names:
            await connection.execute(f"DROP SCHEMA IF EXISTS {name} CASCADE")
        await connection.close()
