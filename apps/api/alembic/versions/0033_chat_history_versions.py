"""Track every committed message mutation without rereading the full history."""

from pathlib import Path

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).parents[1] / "sql/0033_chat_history_versions.sql"
    op.execute(sql.read_text(encoding="utf-8"))


def downgrade() -> None:
    op.execute("LOCK TABLE messages IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM product_generations WHERE status = 'pending') THEN
            RAISE EXCEPTION 'Drain pending answers before history version downgrade';
        END IF;
    END $$;""")
    op.execute("DROP TRIGGER chat_history_changed ON messages")
    op.execute("DROP TRIGGER chat_history_truncated ON messages")
    op.execute("DROP FUNCTION advance_chat_history_version()")
    op.drop_table("chat_history_versions")
