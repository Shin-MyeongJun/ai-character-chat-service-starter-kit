-- Publication snapshots. Also apply this file to existing databases.
BEGIN;

CREATE TABLE IF NOT EXISTS lorebook_snapshots (
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
);

CREATE TABLE IF NOT EXISTS character_snapshots (
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
);

CREATE TABLE IF NOT EXISTS product_snapshots (
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
);

CREATE TABLE IF NOT EXISTS product_snapshot_characters (
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
);

CREATE INDEX IF NOT EXISTS ix_product_snapshot_characters_character ON product_snapshot_characters (character_snapshot_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_product_snapshot_characters_primary ON product_snapshot_characters (product_snapshot_id) WHERE is_primary = true;

CREATE TABLE IF NOT EXISTS product_snapshot_lorebooks (
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
);

CREATE INDEX IF NOT EXISTS ix_product_snapshot_lorebooks_lorebook ON product_snapshot_lorebooks (lorebook_snapshot_id);

COMMIT;
