"""Fence memory result writes and transitions with a unique token per claim.

Stop old memory workers before upgrading; their SQL cannot enforce fencing.
Existing running jobs become eligible for a fresh token after lease expiry.
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_jobs", sa.Column("claim_token", sa.UUID(), nullable=True))


def downgrade() -> None:
    op.execute("LOCK TABLE memory_jobs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM memory_jobs WHERE status = 'running') THEN
            RAISE EXCEPTION 'Stop and drain memory workers before downgrade';
        END IF;
    END $$;""")
    op.drop_column("memory_jobs", "claim_token")
