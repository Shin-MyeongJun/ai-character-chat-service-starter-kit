"""Persist the raw-history prefix requested by answer context compaction."""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_jobs",
        sa.Column("summary_through_position", sa.BigInteger(), nullable=True),
    )
    op.create_check_constraint(
        "ck_memory_jobs_summary_target",
        "memory_jobs",
        "summary_through_position IS NULL OR summary_through_position > 0",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE memory_jobs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM memory_jobs
                   WHERE status = 'running' OR summary_through_position IS NOT NULL) THEN
            RAISE EXCEPTION 'Drain memory compaction requests before downgrade';
        END IF;
    END $$;""")
    op.drop_constraint("ck_memory_jobs_summary_target", "memory_jobs", type_="check")
    op.drop_column("memory_jobs", "summary_through_position")
