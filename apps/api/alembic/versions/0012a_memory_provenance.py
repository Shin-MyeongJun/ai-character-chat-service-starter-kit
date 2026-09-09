from alembic import op

revision = "0012a"
down_revision = "0012"


def upgrade():
    # The original Docker schema already contains this column; retain that data.
    op.execute(
        "ALTER TABLE conversation_memories ADD COLUMN IF NOT EXISTS source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL"
    )


def downgrade():
    raise RuntimeError("Memory provenance must be preserved; use a forward migration.")
