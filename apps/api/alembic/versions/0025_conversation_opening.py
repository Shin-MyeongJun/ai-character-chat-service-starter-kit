"""Separate fixed snapshot starts from legacy message histories."""

from pathlib import Path

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "infra/postgres/init/016_conversation_opening.sql"
    )
    for statement in path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute("LOCK TABLE conversations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM conversations WHERE opening_mode = 'snapshot') THEN
            RAISE EXCEPTION 'Preserve fixed opening contract before downgrade';
        END IF;
    END $$;""")
    op.drop_constraint("ck_conversation_opening_mode", "conversations")
    op.drop_column("conversations", "opening_mode")
