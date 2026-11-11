"""Ordered, immutable image occurrences in the current message revision."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages", sa.Column("content_blocks", postgresql.JSONB(), nullable=True)
    )
    op.create_check_constraint(
        "ck_messages_content_blocks_array",
        "messages",
        "content_blocks IS NULL OR jsonb_typeof(content_blocks) = 'array'",
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM messages WHERE content_blocks IS NOT NULL) THEN
                RAISE EXCEPTION 'Message content blocks exist; downgrade refused';
            END IF;
        END $$;
    """)
    op.drop_constraint("ck_messages_content_blocks_array", "messages", type_="check")
    op.drop_column("messages", "content_blocks")
