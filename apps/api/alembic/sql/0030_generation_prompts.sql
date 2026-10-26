CREATE TABLE generation_prompts (
    generation_id UUID PRIMARY KEY REFERENCES product_generations(id) ON DELETE CASCADE,
    request_json TEXT NOT NULL,
    digest TEXT NOT NULL,
    format_version INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider TEXT NOT NULL,
    max_output_tokens INTEGER NOT NULL,
    CONSTRAINT ck_generation_prompt_format CHECK (format_version = 1),
    CONSTRAINT ck_generation_prompt_digest CHECK (digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_generation_prompt_output CHECK (max_output_tokens > 0)
);
CREATE INDEX ix_generation_created_id ON product_generations(created_at, id);
CREATE INDEX ix_generation_conversation_created ON product_generations(conversation_id, created_at);
