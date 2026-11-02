"""Persist authentication mail intent in the proof transaction."""

from pathlib import Path

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).parents[1] / "sql/0034_auth_mail_outbox.sql"
    # asyncpg prepares one statement per execution; this fixed DDL contains no
    # function bodies or quoted semicolons.
    for statement in sql.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    # Stop API/workers before rollback. Never silently discard queued delivery.
    op.execute("LOCK TABLE auth_mail_outbox IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM auth_mail_outbox WHERE status IN ('pending', 'processing')) THEN
            RAISE EXCEPTION 'Drain authentication mail before downgrade';
        END IF;
    END $$;""")
    op.drop_table("auth_mail_outbox")
