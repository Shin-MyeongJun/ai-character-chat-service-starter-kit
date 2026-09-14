ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS history_revision INTEGER NOT NULL DEFAULT 1;

ALTER TABLE conversation_memories
    ADD COLUMN IF NOT EXISTS embedding_dimension INTEGER,
    ADD COLUMN IF NOT EXISTS embedding_settings JSON,
    ADD COLUMN IF NOT EXISTS embedded_content_digest TEXT,
    ADD COLUMN IF NOT EXISTS index_status TEXT NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS summary_provider TEXT,
    ADD COLUMN IF NOT EXISTS summary_model TEXT,
    ADD COLUMN IF NOT EXISTS prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS source_start_position BIGINT,
    ADD COLUMN IF NOT EXISTS source_end_position BIGINT,
    ADD COLUMN IF NOT EXISTS source_digest TEXT,
    ADD COLUMN IF NOT EXISTS conversation_revision INTEGER,
    ADD COLUMN IF NOT EXISTS summary_input_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS summary_output_tokens INTEGER,
    ADD COLUMN IF NOT EXISTS embedding_tokens INTEGER;

UPDATE conversation_memories
SET index_status = 'ready', embedding_dimension = 1536
WHERE embedding IS NOT NULL
  AND embedding_provider IS NOT NULL
  AND embedding_model IS NOT NULL;

ALTER TABLE conversation_memories
    ADD CONSTRAINT ck_conversation_memories_index_status
        CHECK (index_status IN ('pending', 'ready', 'failed')),
    ADD CONSTRAINT ck_conversation_memories_importance
        CHECK (importance >= 0 AND importance <= 1),
    ADD CONSTRAINT ck_conversation_memories_source_range
        CHECK (source_start_position IS NULL OR source_end_position >= source_start_position),
    ADD CONSTRAINT ck_conversation_memories_ready_embedding
        CHECK (
            index_status <> 'ready'
            OR (
                embedding IS NOT NULL
                AND embedding_provider IS NOT NULL
                AND embedding_model IS NOT NULL
                AND embedding_dimension IS NOT NULL
            )
        ),
    ADD CONSTRAINT uq_conversation_memory_summary_source UNIQUE (
        conversation_id,
        memory_type,
        source_start_position,
        source_end_position,
        conversation_revision,
        prompt_version
    );

CREATE TABLE IF NOT EXISTS memory_jobs (
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
    CONSTRAINT ck_memory_jobs_status
        CHECK (status IN ('pending', 'running', 'idle', 'failed')),
    CONSTRAINT ck_memory_jobs_generation
        CHECK (requested_generation >= completed_generation),
    CONSTRAINT ck_memory_jobs_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS ix_memory_jobs_claim
    ON memory_jobs (status, next_attempt_at, updated_at);
