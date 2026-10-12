"""Add reports, assessments and actions while preserving legacy flags."""

from pathlib import Path

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0027_moderation_review.sql"
    # Freeze the legacy copy during this one-time migration.
    op.execute("LOCK TABLE moderation_flags IN SHARE MODE")
    for statement in path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute(
        "LOCK TABLE moderation_reports, moderation_assessments, moderation_assessment_reports, moderation_actions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM moderation_reports)
        OR EXISTS (SELECT 1 FROM moderation_assessments)
        OR EXISTS (SELECT 1 FROM moderation_actions) THEN
            RAISE EXCEPTION 'Moderation review data exists; preserve it before downgrade';
        END IF;
    END $$;""")
    for table in (
        "moderation_actions",
        "moderation_assessment_reports",
        "moderation_assessments",
        "moderation_reports",
    ):
        op.drop_table(table)
