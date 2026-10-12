"""Moderation DDL parity, legacy provenance and PostgreSQL constraints."""

import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.db.base import Base
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from test_media_migrations import migration_sql
from test_product_migrations import signature

ROOT = Path(__file__).resolve().parents[3]
TABLES = (
    "moderation_reports",
    "moderation_assessments",
    "moderation_assessment_reports",
    "moderation_actions",
)
SQL = ROOT / "apps/api/alembic/sql/0027_moderation_review.sql"


def test_frozen_schema_matches_models_and_initial_sql():
    sql = SQL.read_text(encoding="utf-8")
    assert sql == (ROOT / "infra/postgres/init/018_moderation_review.sql").read_text(
        encoding="utf-8"
    )
    dialect = postgresql.dialect()
    for name in TABLES:
        table = Base.metadata.tables[name]
        assert str(CreateTable(table).compile(dialect=dialect)).strip() + ";" in sql
        for index in table.indexes:
            assert str(CreateIndex(index).compile(dialect=dialect)).strip() + ";" in sql
        assert all(fk.ondelete != "CASCADE" for fk in table.foreign_keys)


def test_offline_migration_chain_and_preservation_guard():
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

    upgrade = render("upgrade", "0026:0027")
    downgrade = render("downgrade", "0027:0026")
    assert "LOCK TABLE moderation_flags IN SHARE MODE" in upgrade
    for name in TABLES:
        assert f"CREATE TABLE {name}" in upgrade
        assert f"DROP TABLE {name}" in downgrade
    assert "INSERT INTO moderation_reports" in upgrade
    assert "legacy_unclassified" in upgrade
    assert "preserve it before downgrade" in downgrade
    assert "DROP TABLE moderation_flags" not in downgrade
    assert "DROP TABLE audit_logs" not in downgrade


@pytest.mark.asyncio
async def test_moderation_migration_preserves_legacy_and_matches_orm(db):
    engine = db.bind
    upgrade = await migration_sql("upgrade", "0026:0027")
    downgrade = await migration_sql("downgrade", "0027:0026")
    async with engine.connect() as conn:
        original = await conn.scalar(text("SELECT current_schema()"))
        expected = await conn.run_sync(signature, original)
    raw = await engine.raw_connection()
    connection = raw.driver_connection
    schema = "moderation_migration_" + uuid4().hex
    try:
        await connection.execute(f"CREATE SCHEMA {schema}")
        await connection.execute(f"SET search_path TO {schema},public")
        # Complete pre-0027 schema from current metadata, excluding new tables.
        from sqlalchemy.schema import CreateTable as DDLTable

        for table in Base.metadata.sorted_tables:
            if table.name not in TABLES:
                await connection.execute(
                    str(DDLTable(table).compile(dialect=postgresql.dialect()))
                )
        await connection.execute(
            "CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('0026')"
        )
        user_id = uuid4()
        await connection.execute(
            "INSERT INTO users(id,email) VALUES($1,'review@example.test')", user_id
        )
        ids = [uuid4() for _ in range(3)]
        for flag_id, status in zip(ids, ("pending", "reviewed", "dismissed")):
            await connection.execute(
                "INSERT INTO moderation_flags(id,target_type,target_id,flagged_by,reason,status,reviewed_by,reviewed_at) VALUES($1,'character',$2,$3,'original reason',$4,$3,now())",
                flag_id,
                uuid4(),
                user_id,
                status,
            )
        await connection.execute(upgrade)
        assert await connection.fetchval("SELECT count(*) FROM moderation_flags") == 3
        rows = await connection.fetch(
            "SELECT id,request_key,reason_code,reason_detail,evidence_snapshot->'legacy_moderation_flag'->>'status' AS legacy_status FROM moderation_reports ORDER BY legacy_status"
        )
        assert {r["id"] for r in rows} == set(ids)
        assert {r["legacy_status"] for r in rows} == {
            "pending",
            "reviewed",
            "dismissed",
        }
        assert all(
            r["id"] == r["request_key"]
            and r["reason_code"] == "legacy_unclassified"
            and r["reason_detail"] == "original reason"
            for r in rows
        )
        assert (
            await connection.fetchval("SELECT count(*) FROM moderation_assessments")
            == 0
        )
        async with engine.connect() as conn:
            actual = await conn.run_sync(signature, schema)
        assert {k: actual[k] for k in TABLES} == {k: expected[k] for k in TABLES}
        await connection.execute("DELETE FROM users WHERE id=$1", user_id)
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM moderation_reports WHERE reporter_user_id IS NULL"
            )
            == 3
        )
        with pytest.raises(Exception, match="preserve it before downgrade"):
            await connection.execute(downgrade)
        await connection.execute("ROLLBACK")
    finally:
        await connection.execute(f"SET search_path TO {original},public")
        await connection.execute(f"DROP SCHEMA {schema} CASCADE")
        raw.close()


@pytest.mark.asyncio
async def test_moderation_links_constraints_and_history_retention(db):
    from app.db.models.moderation_review import (
        ModerationAction,
        ModerationAssessment,
        ModerationAssessmentReport,
        ModerationReport,
    )

    target = uuid4()
    reports = [
        ModerationReport(
            request_key=uuid4(),
            target_type="product",
            target_id=target,
            reason_code="abuse",
        )
        for _ in range(2)
    ]
    assessments = [
        ModerationAssessment(
            target_type="product",
            target_id=target,
            assessment_type="automatic",
            policy_version="v1",
            outcome="insufficient_evidence",
            rationale="needs review",
            evaluation_key=str(uuid4()),
        )
        for _ in range(2)
    ]
    db.add_all(reports + assessments)
    await db.flush()
    db.add_all(
        [
            ModerationAssessmentReport(
                assessment_id=a.id, report_id=r.id, disposition="unassessed"
            )
            for a in assessments
            for r in reports
        ]
    )
    actions = [
        ModerationAction(
            assessment_id=assessments[0].id,
            target_type="product",
            target_id=target,
            action_type="restrict",
            scope="product_access",
            starts_at=text("now()"),
            idempotency_key=uuid4(),
        )
        for _ in range(2)
    ]
    db.add_all(actions)
    await db.flush()
    assert (
        await db.scalar(text("SELECT count(*) FROM moderation_assessment_reports")) == 4
    )
    assert await db.scalar(text("SELECT count(*) FROM moderation_actions")) == 2

    bad_statements = [
        (
            "UPDATE moderation_reports SET form_elapsed_ms=-1 WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_reports SET target_type='invalid' WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_reports SET evidence_snapshot='[]' WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_reports SET attachment_refs='{}' WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_reports SET intake_status='duplicate',duplicate_of_report_id=id WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_reports SET request_key=(SELECT request_key FROM moderation_reports WHERE id<>:id LIMIT 1) WHERE id=:id",
            reports[0].id,
        ),
        (
            "UPDATE moderation_assessments SET confidence_score=2 WHERE id=:id",
            assessments[0].id,
        ),
        (
            "UPDATE moderation_assessments SET window_start=now(),window_end=now() WHERE id=:id",
            assessments[0].id,
        ),
        (
            "UPDATE moderation_assessments SET supersedes_assessment_id=id WHERE id=:id",
            assessments[0].id,
        ),
        ("UPDATE moderation_actions SET ends_at=starts_at WHERE id=:id", actions[0].id),
        ("UPDATE moderation_actions SET status='applied' WHERE id=:id", actions[0].id),
        (
            "UPDATE moderation_actions SET assessment_id='00000000-0000-0000-0000-000000000000' WHERE id=:id",
            actions[0].id,
        ),
        ("DELETE FROM moderation_reports WHERE id=:id", reports[0].id),
        ("DELETE FROM moderation_assessments WHERE id=:id", assessments[0].id),
    ]
    from sqlalchemy.exc import IntegrityError

    for statement, row_id in bad_statements:
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(text(statement), {"id": row_id})
