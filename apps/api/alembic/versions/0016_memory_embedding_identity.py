"""Track embedding identity without assuming legacy-vector compatibility."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE conversation_memories "
        "ADD COLUMN embedding_provider TEXT, "
        "ADD COLUMN embedding_model TEXT"
    )
    op.execute(
        "ALTER TABLE conversation_memories "
        "ADD CONSTRAINT ck_conversation_memories_embedding_identity "
        "CHECK ((embedding_provider IS NULL) = (embedding_model IS NULL))"
    )
    op.execute(
        "CREATE INDEX ix_conversation_memories_embedding_identity "
        "ON conversation_memories (embedding_provider, embedding_model)"
    )


def downgrade():
    op.drop_index(
        "ix_conversation_memories_embedding_identity",
        table_name="conversation_memories",
    )
    op.drop_constraint(
        "ck_conversation_memories_embedding_identity",
        "conversation_memories",
        type_="check",
    )
    op.drop_column("conversation_memories", "embedding_model")
    op.drop_column("conversation_memories", "embedding_provider")
