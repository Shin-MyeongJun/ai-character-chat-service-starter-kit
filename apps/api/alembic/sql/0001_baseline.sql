CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE providers (
	name TEXT NOT NULL, 
	is_enabled BOOLEAN DEFAULT true NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
)

;

CREATE TABLE subscription_plans (
	name TEXT NOT NULL, 
	monthly_credit BIGINT NOT NULL, 
	price NUMERIC(10, 2) NOT NULL, 
	billing_cycle TEXT NOT NULL, 
	is_enabled BOOLEAN DEFAULT true NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_subscription_plans_billing_cycle CHECK (billing_cycle IN ('monthly', 'yearly'))
)

;

CREATE TABLE users (
	email TEXT NOT NULL, 
	password_hash TEXT, 
	display_name TEXT, 
	role TEXT DEFAULT 'user' NOT NULL, 
	status TEXT DEFAULT 'active' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_role CHECK (role IN ('user', 'admin')), 
	CONSTRAINT ck_users_status CHECK (status IN ('active', 'suspended', 'banned')), 
	UNIQUE (email)
)

;

CREATE TABLE audit_logs (
	admin_id UUID NOT NULL, 
	action TEXT NOT NULL, 
	target_id UUID, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(admin_id) REFERENCES users (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_audit_logs_admin_id_created_at ON audit_logs (admin_id, created_at);
CREATE INDEX ix_audit_logs_action_created_at ON audit_logs (action, created_at);

CREATE TABLE credit_accounts (
	user_id UUID NOT NULL, 
	balance BIGINT DEFAULT 0 NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (user_id), 
	CONSTRAINT ck_credit_accounts_balance_non_negative CHECK (balance >= 0), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;

CREATE TABLE credit_transactions (
	user_id UUID NOT NULL, 
	amount BIGINT NOT NULL, 
	reason TEXT NOT NULL, 
	reference_id UUID, 
	idempotency_key TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_credit_transactions_reason CHECK (reason IN ('chat_usage', 'purchase', 'refund', 'subscription_grant')), 
	CONSTRAINT uq_credit_transactions_idempotency_key UNIQUE (idempotency_key), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_credit_transactions_user_id_created_at ON credit_transactions (user_id, created_at);

CREATE TABLE lorebooks (
	owner_id UUID NOT NULL, 
	title TEXT NOT NULL, 
	description TEXT, 
	visibility TEXT DEFAULT 'private' NOT NULL, 
	status TEXT DEFAULT 'draft' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_lorebooks_visibility CHECK (visibility IN ('private', 'public', 'unlisted')), 
	CONSTRAINT ck_lorebooks_status CHECK (status IN ('draft', 'approved', 'rejected')), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_lorebooks_owner_id ON lorebooks (owner_id);

CREATE TABLE models (
	provider_id UUID NOT NULL, 
	model_name TEXT NOT NULL, 
	display_name TEXT NOT NULL, 
	context_window INTEGER NOT NULL, 
	input_price NUMERIC(10, 6) NOT NULL, 
	output_price NUMERIC(10, 6) NOT NULL, 
	capabilities JSONB DEFAULT '{}'::jsonb NOT NULL, 
	is_enabled BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_models_provider_model_name UNIQUE (provider_id, model_name), 
	FOREIGN KEY(provider_id) REFERENCES providers (id) ON DELETE RESTRICT
)

;

CREATE TABLE moderation_flags (
	target_type TEXT NOT NULL, 
	target_id UUID NOT NULL, 
	flagged_by UUID, 
	reason TEXT NOT NULL, 
	status TEXT DEFAULT 'pending' NOT NULL, 
	reviewed_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_moderation_flags_target_type CHECK (target_type IN ('character', 'message')), 
	CONSTRAINT ck_moderation_flags_status CHECK (status IN ('pending', 'reviewed', 'dismissed')), 
	FOREIGN KEY(flagged_by) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_moderation_flags_status_created_at ON moderation_flags (status, created_at);
CREATE INDEX ix_moderation_flags_target ON moderation_flags (target_type, target_id);

CREATE TABLE user_oauth_accounts (
	user_id UUID NOT NULL, 
	provider TEXT NOT NULL, 
	provider_user_id TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_oauth_provider_user UNIQUE (provider, provider_user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;

CREATE TABLE user_subscriptions (
	user_id UUID NOT NULL, 
	plan_id UUID NOT NULL, 
	status TEXT NOT NULL, 
	current_period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	current_period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_user_subscriptions_status CHECK (status IN ('active', 'canceled', 'expired', 'past_due')), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(plan_id) REFERENCES subscription_plans (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_user_subscriptions_user_id_status ON user_subscriptions (user_id, status);

CREATE TABLE characters (
	owner_id UUID NOT NULL, 
	name TEXT NOT NULL, 
	description TEXT, 
	persona_prompt TEXT NOT NULL, 
	visibility TEXT DEFAULT 'private' NOT NULL, 
	status TEXT DEFAULT 'draft' NOT NULL, 
	default_model_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_characters_visibility CHECK (visibility IN ('private', 'public', 'unlisted')), 
	CONSTRAINT ck_characters_status CHECK (status IN ('draft', 'approved', 'rejected')), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(default_model_id) REFERENCES models (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_characters_owner_id ON characters (owner_id);

CREATE TABLE lorebook_entries (
	lorebook_id UUID NOT NULL, 
	title TEXT, 
	content TEXT NOT NULL, 
	entry_type TEXT DEFAULT 'world' NOT NULL, 
	activation_type TEXT DEFAULT 'always' NOT NULL, 
	key_triggers TEXT[], 
	match_mode TEXT DEFAULT 'contains' NOT NULL, 
	priority INTEGER DEFAULT 0 NOT NULL, 
	token_budget INTEGER, 
	placement TEXT DEFAULT 'before_history' NOT NULL, 
	is_enabled BOOLEAN DEFAULT true NOT NULL, 
	metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
	embedding VECTOR(1536), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_lorebook_entries_entry_type CHECK (entry_type IN ('author_note', 'world', 'genre', 'rule', 'location', 'faction', 'character_relation', 'event', 'term', 'secret')), 
	CONSTRAINT ck_lorebook_entries_activation_type CHECK (activation_type IN ('always', 'keyword', 'semantic', 'manual')), 
	CONSTRAINT ck_lorebook_entries_match_mode CHECK (match_mode IN ('exact', 'contains', 'regex')), 
	CONSTRAINT ck_lorebook_entries_keyword_triggers CHECK (activation_type <> 'keyword' OR is_enabled = false OR (key_triggers IS NOT NULL AND cardinality(key_triggers) > 0)), 
	CONSTRAINT ck_lorebook_entries_token_budget CHECK (token_budget IS NULL OR token_budget >= 0), 
	CONSTRAINT ck_lorebook_entries_placement CHECK (placement IN ('system_top', 'before_memory', 'after_memory', 'before_history', 'near_user_message')), 
	FOREIGN KEY(lorebook_id) REFERENCES lorebooks (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_lorebook_entries_lorebook_id ON lorebook_entries (lorebook_id);
CREATE INDEX ix_lorebook_entries_embedding ON lorebook_entries USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE lorebook_snapshots (
	lorebook_id UUID, 
	version INTEGER NOT NULL, 
	snapshot_schema_version INTEGER DEFAULT 1 NOT NULL, 
	snapshot_data JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lorebook_snapshots_version UNIQUE (lorebook_id, version), 
	CONSTRAINT ck_lorebook_snapshots_version CHECK (version > 0), 
	CONSTRAINT ck_lorebook_snapshots_schema_version CHECK (snapshot_schema_version > 0), 
	CONSTRAINT ck_lorebook_snapshots_data_object CHECK (jsonb_typeof(snapshot_data) = 'object'), 
	FOREIGN KEY(lorebook_id) REFERENCES lorebooks (id) ON DELETE SET NULL
)

;

CREATE TABLE payments (
	user_id UUID NOT NULL, 
	subscription_id UUID, 
	amount NUMERIC(10, 2) NOT NULL, 
	currency TEXT DEFAULT 'KRW' NOT NULL, 
	status TEXT NOT NULL, 
	pg_provider TEXT NOT NULL, 
	pg_transaction_id TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_payments_status CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded')), 
	CONSTRAINT uq_payments_pg_transaction_id UNIQUE (pg_transaction_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(subscription_id) REFERENCES user_subscriptions (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_payments_user_id_created_at ON payments (user_id, created_at);

CREATE TABLE products (
	owner_id UUID NOT NULL, 
	title TEXT NOT NULL, 
	description TEXT, 
	opening_message TEXT, 
	visibility TEXT DEFAULT 'private' NOT NULL, 
	status TEXT DEFAULT 'draft' NOT NULL, 
	default_model_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_products_visibility CHECK (visibility IN ('private', 'public', 'unlisted')), 
	CONSTRAINT ck_products_status CHECK (status IN ('draft', 'approved', 'rejected')), 
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(default_model_id) REFERENCES models (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_products_owner_id ON products (owner_id);

CREATE TABLE character_assets (
	character_id UUID NOT NULL, 
	asset_type TEXT NOT NULL, 
	purpose TEXT NOT NULL, 
	file_url TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_character_assets_asset_type CHECK (asset_type IN ('image', 'audio', 'video')), 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_character_assets_character_id ON character_assets (character_id);

CREATE TABLE character_images (
	character_id UUID NOT NULL, 
	emotion_tag TEXT NOT NULL, 
	image_url TEXT NOT NULL, 
	is_default BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_character_images_emotion UNIQUE (character_id, emotion_tag), 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE
)

;
CREATE UNIQUE INDEX uq_character_images_default_per_character ON character_images (character_id) WHERE is_default = true;

CREATE TABLE character_snapshots (
	character_id UUID, 
	version INTEGER NOT NULL, 
	snapshot_schema_version INTEGER DEFAULT 1 NOT NULL, 
	snapshot_data JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_character_snapshots_version UNIQUE (character_id, version), 
	CONSTRAINT ck_character_snapshots_version CHECK (version > 0), 
	CONSTRAINT ck_character_snapshots_schema_version CHECK (snapshot_schema_version > 0), 
	CONSTRAINT ck_character_snapshots_data_object CHECK (jsonb_typeof(snapshot_data) = 'object'), 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE SET NULL
)

;

CREATE TABLE conversations (
	user_id UUID NOT NULL, 
	product_id UUID NOT NULL, 
	title TEXT, 
	is_group BOOLEAN DEFAULT false NOT NULL, 
	active_model_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE RESTRICT, 
	FOREIGN KEY(active_model_id) REFERENCES models (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_conversations_user_id_created_at ON conversations (user_id, created_at);
CREATE INDEX ix_conversations_product_id_created_at ON conversations (product_id, created_at);

CREATE TABLE product_characters (
	product_id UUID NOT NULL, 
	character_id UUID NOT NULL, 
	role_order INTEGER DEFAULT 0 NOT NULL, 
	role_name TEXT, 
	is_primary BOOLEAN DEFAULT false NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_product_characters_pair UNIQUE (product_id, character_id), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE
)

;
CREATE UNIQUE INDEX uq_product_characters_primary_per_product ON product_characters (product_id) WHERE is_primary = true;
CREATE INDEX ix_product_characters_product_id ON product_characters (product_id);

CREATE TABLE product_lorebooks (
	product_id UUID NOT NULL, 
	lorebook_id UUID NOT NULL, 
	role TEXT DEFAULT 'detail' NOT NULL, 
	priority INTEGER DEFAULT 0 NOT NULL, 
	is_required BOOLEAN DEFAULT true NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_product_lorebooks_role CHECK (role IN ('main', 'detail', 'rule', 'optional')), 
	CONSTRAINT uq_product_lorebooks_pair UNIQUE (product_id, lorebook_id), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(lorebook_id) REFERENCES lorebooks (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_product_lorebooks_product_id ON product_lorebooks (product_id);

CREATE TABLE product_snapshots (
	product_id UUID, 
	version INTEGER NOT NULL, 
	snapshot_schema_version INTEGER DEFAULT 1 NOT NULL, 
	snapshot_data JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_product_snapshots_version UNIQUE (product_id, version), 
	CONSTRAINT ck_product_snapshots_version CHECK (version > 0), 
	CONSTRAINT ck_product_snapshots_schema_version CHECK (snapshot_schema_version > 0), 
	CONSTRAINT ck_product_snapshots_data_object CHECK (jsonb_typeof(snapshot_data) = 'object'), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE SET NULL
)

;

CREATE TABLE conversation_characters (
	conversation_id UUID NOT NULL, 
	character_id UUID NOT NULL, 
	role_order INTEGER DEFAULT 0 NOT NULL, 
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_conversation_characters_pair UNIQUE (conversation_id, character_id), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_conversation_characters_conversation_id ON conversation_characters (conversation_id);

CREATE TABLE conversation_memories (
	conversation_id UUID NOT NULL, 
	memory_type TEXT NOT NULL, 
	content TEXT NOT NULL, 
	embedding VECTOR(1536), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_conversation_memories_memory_type CHECK (memory_type IN ('summary', 'fact', 'event')), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_conversation_memories_conversation_id ON conversation_memories (conversation_id);
CREATE INDEX ix_conversation_memories_embedding ON conversation_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE TABLE messages (
	conversation_id UUID NOT NULL, 
	sender_type TEXT NOT NULL, 
	character_id UUID, 
	content TEXT NOT NULL, 
	emotion_tag TEXT, 
	token_count INTEGER, 
	model_id UUID, 
	generated_by_ai BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_messages_sender_type CHECK (sender_type IN ('user', 'character', 'system')), 
	CONSTRAINT ck_messages_character_sender_has_character CHECK ((sender_type <> 'character') OR (character_id IS NOT NULL)), 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE SET NULL, 
	FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_messages_model_id_created_at ON messages (model_id, created_at);
CREATE INDEX ix_messages_conversation_id_created_at ON messages (conversation_id, created_at);

CREATE TABLE product_snapshot_characters (
	product_snapshot_id UUID NOT NULL, 
	character_snapshot_id UUID NOT NULL, 
	role_order INTEGER DEFAULT 0 NOT NULL, 
	role_name TEXT, 
	is_primary BOOLEAN DEFAULT false NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_product_snapshot_characters_pair UNIQUE (product_snapshot_id, character_snapshot_id), 
	FOREIGN KEY(product_snapshot_id) REFERENCES product_snapshots (id) ON DELETE CASCADE, 
	FOREIGN KEY(character_snapshot_id) REFERENCES character_snapshots (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_product_snapshot_characters_character ON product_snapshot_characters (character_snapshot_id);
CREATE UNIQUE INDEX uq_product_snapshot_characters_primary ON product_snapshot_characters (product_snapshot_id) WHERE is_primary = true;

CREATE TABLE product_snapshot_lorebooks (
	product_snapshot_id UUID NOT NULL, 
	lorebook_snapshot_id UUID NOT NULL, 
	role TEXT DEFAULT 'detail' NOT NULL, 
	priority INTEGER DEFAULT 0 NOT NULL, 
	is_required BOOLEAN DEFAULT true NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_product_snapshot_lorebooks_pair UNIQUE (product_snapshot_id, lorebook_snapshot_id), 
	CONSTRAINT ck_product_snapshot_lorebooks_role CHECK (role IN ('main', 'detail', 'rule', 'optional')), 
	FOREIGN KEY(product_snapshot_id) REFERENCES product_snapshots (id) ON DELETE CASCADE, 
	FOREIGN KEY(lorebook_snapshot_id) REFERENCES lorebook_snapshots (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_product_snapshot_lorebooks_lorebook ON product_snapshot_lorebooks (lorebook_snapshot_id);

CREATE TABLE usage_logs (
	user_id UUID NOT NULL, 
	conversation_id UUID, 
	model_id UUID NOT NULL, 
	input_tokens INTEGER NOT NULL, 
	output_tokens INTEGER NOT NULL, 
	latency_ms INTEGER, 
	cost_credit BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE SET NULL, 
	FOREIGN KEY(model_id) REFERENCES models (id) ON DELETE RESTRICT
)

;
CREATE INDEX ix_usage_logs_conversation_id_created_at ON usage_logs (conversation_id, created_at);
CREATE INDEX ix_usage_logs_user_id_created_at ON usage_logs (user_id, created_at);