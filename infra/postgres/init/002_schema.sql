CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'user'
        CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')),
    status TEXT NOT NULL DEFAULT 'active'
        CONSTRAINT ck_users_status CHECK (status IN ('active', 'suspended', 'banned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_oauth_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_oauth_provider_user UNIQUE (provider, provider_user_id)
);

CREATE TABLE IF NOT EXISTS providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    is_enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    model_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    context_window INT NOT NULL,
    input_price NUMERIC(10, 6) NOT NULL,
    output_price NUMERIC(10, 6) NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_models_provider_model_name UNIQUE (provider_id, model_name)
);

CREATE TABLE IF NOT EXISTS characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    persona_prompt TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'private'
        CONSTRAINT ck_characters_visibility CHECK (visibility IN ('private', 'public', 'unlisted')),
    status TEXT NOT NULL DEFAULT 'draft'
        CONSTRAINT ck_characters_status CHECK (status IN ('draft', 'approved', 'rejected')),
    default_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_characters_owner_id
    ON characters (owner_id);

CREATE TABLE IF NOT EXISTS character_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    emotion_tag TEXT NOT NULL,
    image_url TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_character_images_emotion UNIQUE (character_id, emotion_tag)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_character_images_default_per_character
    ON character_images (character_id)
    WHERE is_default = true;

CREATE TABLE IF NOT EXISTS character_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    asset_type TEXT NOT NULL
        CONSTRAINT ck_character_assets_asset_type CHECK (asset_type IN ('image', 'audio', 'video')),
    purpose TEXT NOT NULL,
    file_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_character_assets_character_id
    ON character_assets (character_id);

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    is_group BOOLEAN NOT NULL DEFAULT false,
    active_model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_conversations_user_id_created_at
    ON conversations (user_id, created_at);

CREATE TABLE IF NOT EXISTS conversation_characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    role_order INT NOT NULL DEFAULT 0,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_conversation_characters_pair UNIQUE (conversation_id, character_id)
);

CREATE INDEX IF NOT EXISTS ix_conversation_characters_conversation_id
    ON conversation_characters (conversation_id);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_type TEXT NOT NULL
        CONSTRAINT ck_messages_sender_type CHECK (sender_type IN ('user', 'character', 'system')),
    character_id UUID REFERENCES characters(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    emotion_tag TEXT,
    token_count INT,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    generated_by_ai BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_messages_character_sender_has_character
        CHECK ((sender_type <> 'character') OR (character_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_id_created_at
    ON messages (conversation_id, created_at);

CREATE INDEX IF NOT EXISTS ix_messages_model_id_created_at
    ON messages (model_id, created_at);

CREATE TABLE IF NOT EXISTS lorebook_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id UUID NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    key_trigger TEXT[],
    content TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_lorebook_entries_character_id
    ON lorebook_entries (character_id);

CREATE INDEX IF NOT EXISTS ix_lorebook_entries_embedding
    ON lorebook_entries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS conversation_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    memory_type TEXT NOT NULL
        CONSTRAINT ck_conversation_memories_memory_type
        CHECK (memory_type IN ('summary', 'fact', 'event')),
    content TEXT NOT NULL,
    embedding vector(1536),
    source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_conversation_memories_conversation_id
    ON conversation_memories (conversation_id);

CREATE INDEX IF NOT EXISTS ix_conversation_memories_embedding
    ON conversation_memories
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS credit_accounts (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    balance BIGINT NOT NULL DEFAULT 0
        CONSTRAINT ck_credit_accounts_balance_non_negative CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS credit_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount BIGINT NOT NULL,
    reason TEXT NOT NULL
        CONSTRAINT ck_credit_transactions_reason
        CHECK (reason IN ('chat_usage', 'purchase', 'refund', 'subscription_grant')),
    reference_id UUID,
    idempotency_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_credit_transactions_idempotency_key UNIQUE (idempotency_key)
);

-- If a chat request is retried with the same idempotency_key, this UNIQUE
-- constraint lets only the first debit insert succeed. The retry fails at DB
-- constraint level, so an application bug cannot double-charge the same request.

CREATE INDEX IF NOT EXISTS ix_credit_transactions_user_id_created_at
    ON credit_transactions (user_id, created_at);

CREATE TABLE IF NOT EXISTS usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE RESTRICT,
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    latency_ms INT,
    cost_credit BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_usage_logs_user_id_created_at
    ON usage_logs (user_id, created_at);

CREATE INDEX IF NOT EXISTS ix_usage_logs_conversation_id_created_at
    ON usage_logs (conversation_id, created_at);

CREATE TABLE IF NOT EXISTS subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    monthly_credit BIGINT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    billing_cycle TEXT NOT NULL
        CONSTRAINT ck_subscription_plans_billing_cycle CHECK (billing_cycle IN ('monthly', 'yearly')),
    is_enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES subscription_plans(id) ON DELETE RESTRICT,
    status TEXT NOT NULL
        CONSTRAINT ck_user_subscriptions_status
        CHECK (status IN ('active', 'canceled', 'expired', 'past_due')),
    current_period_start TIMESTAMPTZ NOT NULL,
    current_period_end TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_user_subscriptions_user_id_status
    ON user_subscriptions (user_id, status);

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES user_subscriptions(id) ON DELETE SET NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'KRW',
    status TEXT NOT NULL
        CONSTRAINT ck_payments_status CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded')),
    pg_provider TEXT NOT NULL,
    pg_transaction_id TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_payments_user_id_created_at
    ON payments (user_id, created_at);

CREATE TABLE IF NOT EXISTS moderation_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type TEXT NOT NULL
        CONSTRAINT ck_moderation_flags_target_type CHECK (target_type IN ('character', 'message')),
    target_id UUID NOT NULL,
    flagged_by UUID REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CONSTRAINT ck_moderation_flags_status CHECK (status IN ('pending', 'reviewed', 'dismissed')),
    reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_moderation_flags_status_created_at
    ON moderation_flags (status, created_at);

CREATE INDEX IF NOT EXISTS ix_moderation_flags_target
    ON moderation_flags (target_type, target_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    action TEXT NOT NULL,
    target_id UUID,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_admin_id_created_at
    ON audit_logs (admin_id, created_at);

CREATE INDEX IF NOT EXISTS ix_audit_logs_action_created_at
    ON audit_logs (action, created_at);
