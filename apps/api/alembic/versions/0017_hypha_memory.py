"""Durable Hypha summaries, embedding state, and memory work queue."""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE conversations ADD COLUMN history_revision INTEGER NOT NULL DEFAULT 1"
    )
    op.execute("""ALTER TABLE conversation_memories
        ADD COLUMN embedding_dimension INTEGER,
        ADD COLUMN embedding_settings JSON,
        ADD COLUMN embedded_content_digest TEXT,
        ADD COLUMN index_status TEXT NOT NULL DEFAULT 'pending',
        ADD COLUMN importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
        ADD COLUMN summary_provider TEXT,
        ADD COLUMN summary_model TEXT,
        ADD COLUMN prompt_version TEXT,
        ADD COLUMN source_start_position BIGINT,
        ADD COLUMN source_end_position BIGINT,
        ADD COLUMN source_digest TEXT,
        ADD COLUMN conversation_revision INTEGER,
        ADD COLUMN summary_input_tokens INTEGER,
        ADD COLUMN summary_output_tokens INTEGER,
        ADD COLUMN embedding_tokens INTEGER""")
    op.execute(
        "UPDATE conversation_memories SET index_status = 'ready', embedding_dimension = 1536 "
        "WHERE embedding IS NOT NULL AND embedding_provider IS NOT NULL "
        "AND embedding_model IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE conversation_memories ADD CONSTRAINT "
        "ck_conversation_memories_index_status CHECK "
        "(index_status IN ('pending', 'ready', 'failed'))"
    )
    op.execute(
        "ALTER TABLE conversation_memories ADD CONSTRAINT "
        "ck_conversation_memories_importance CHECK (importance >= 0 AND importance <= 1)"
    )
    op.execute(
        "ALTER TABLE conversation_memories ADD CONSTRAINT "
        "ck_conversation_memories_source_range CHECK "
        "(source_start_position IS NULL OR source_end_position >= source_start_position)"
    )
    op.execute(
        "ALTER TABLE conversation_memories ADD CONSTRAINT "
        "ck_conversation_memories_ready_embedding CHECK "
        "(index_status <> 'ready' OR (embedding IS NOT NULL AND embedding_provider IS NOT NULL "
        "AND embedding_model IS NOT NULL AND embedding_dimension IS NOT NULL))"
    )
    op.execute("""ALTER TABLE conversation_memories ADD CONSTRAINT
        uq_conversation_memory_summary_source UNIQUE
        (conversation_id, memory_type, source_start_position, source_end_position,
         conversation_revision, prompt_version)""")
    op.execute("""CREATE TABLE memory_jobs (
        conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
        owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        requested_generation BIGINT NOT NULL DEFAULT 1,
        completed_generation BIGINT NOT NULL DEFAULT 0,
        scope_generation BIGINT,
        status TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        lease_owner TEXT,
        leased_until TIMESTAMPTZ,
        next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_error_kind TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_memory_jobs_status CHECK (status IN ('pending','running','idle','failed')),
        CONSTRAINT ck_memory_jobs_generation CHECK (requested_generation >= completed_generation),
        CONSTRAINT ck_memory_jobs_attempt_count CHECK (attempt_count >= 0)
    )""")
    op.execute(
        "CREATE INDEX ix_memory_jobs_claim ON memory_jobs "
        "(status, next_attempt_at, updated_at)"
    )


def downgrade():
    op.drop_table("memory_jobs")
    op.drop_constraint(
        "uq_conversation_memory_summary_source", "conversation_memories", type_="unique"
    )
    for name in (
        "ck_conversation_memories_ready_embedding",
        "ck_conversation_memories_source_range",
        "ck_conversation_memories_importance",
        "ck_conversation_memories_index_status",
    ):
        op.drop_constraint(name, "conversation_memories", type_="check")
    for column in (
        "embedding_tokens",
        "summary_output_tokens",
        "summary_input_tokens",
        "conversation_revision",
        "source_digest",
        "source_end_position",
        "source_start_position",
        "prompt_version",
        "summary_model",
        "summary_provider",
        "importance",
        "index_status",
        "embedded_content_digest",
        "embedding_settings",
        "embedding_dimension",
    ):
        op.drop_column("conversation_memories", column)
    op.drop_column("conversations", "history_revision")
