BEGIN;

-- Running upgrade 0001 -> 0002

ALTER TABLE product_characters ADD CONSTRAINT uq_product_characters_product_identity UNIQUE (product_id, id);

ALTER TABLE product_lorebooks ADD CONSTRAINT uq_product_lorebooks_product_identity UNIQUE (product_id, id);

ALTER TABLE product_lorebooks ADD COLUMN scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all', 'selected'));

CREATE TABLE product_lorebook_characters (
        product_id UUID NOT NULL,
        product_character_id UUID NOT NULL,
        product_lorebook_id UUID NOT NULL,
        PRIMARY KEY (product_character_id, product_lorebook_id),
        FOREIGN KEY (product_id, product_character_id) REFERENCES product_characters(product_id, id) ON DELETE CASCADE,
        FOREIGN KEY (product_id, product_lorebook_id) REFERENCES product_lorebooks(product_id, id) ON DELETE CASCADE
    );


-- Running upgrade 0002 -> 0003

ALTER TABLE lorebook_entries DROP CONSTRAINT ck_lorebook_entries_entry_type;

ALTER TABLE lorebook_entries ADD CONSTRAINT ck_lorebook_entries_entry_type CHECK (entry_type IN ('author_note','world','genre','rule','location','faction','character_relation','event','term','secret','start_set'));


-- Running upgrade 0003 -> 0004

ALTER TABLE products ADD COLUMN reasoning_effort TEXT;

ALTER TABLE products ADD COLUMN replacement_policy JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE lorebook_entries ADD CONSTRAINT uq_lorebook_entries_identity UNIQUE (lorebook_id,id);

CREATE TABLE product_start_sets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), product_id UUID NOT NULL,
        lorebook_id UUID NOT NULL, entry_id UUID NOT NULL, sort_order INTEGER NOT NULL,
        UNIQUE (product_id,entry_id),
        FOREIGN KEY (product_id,lorebook_id) REFERENCES product_lorebooks(product_id,lorebook_id) ON DELETE CASCADE,
        FOREIGN KEY (lorebook_id,entry_id) REFERENCES lorebook_entries(lorebook_id,id) ON DELETE CASCADE);


-- Running upgrade 0004 -> 0005

CREATE TABLE character_snapshot_images (
    character_snapshot_id UUID NOT NULL, 
    source_image_id UUID NOT NULL, 
    emotion_tag TEXT NOT NULL, 
    image_url TEXT NOT NULL, 
    is_default BOOLEAN NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_snapshot_image_emotion UNIQUE (character_snapshot_id, emotion_tag), 
    FOREIGN KEY(character_snapshot_id) REFERENCES character_snapshots (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_snapshot_image_default ON character_snapshot_images (character_snapshot_id) WHERE is_default = true;

CREATE TABLE character_snapshot_assets (
    character_snapshot_id UUID NOT NULL, 
    source_asset_id UUID NOT NULL, 
    asset_type TEXT NOT NULL, 
    purpose TEXT NOT NULL, 
    file_url TEXT NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_snapshot_asset_type CHECK (asset_type IN ('image','audio','video')), 
    FOREIGN KEY(character_snapshot_id) REFERENCES character_snapshots (id) ON DELETE CASCADE
);

CREATE INDEX ix_snapshot_assets_parent ON character_snapshot_assets (character_snapshot_id);


-- Running upgrade 0005 -> 0006

ALTER TABLE product_snapshots ADD CONSTRAINT uq_product_snapshot_identity UNIQUE (product_id,id);

ALTER TABLE products ADD COLUMN latest_snapshot_id UUID;

ALTER TABLE products ADD CONSTRAINT fk_product_latest_snapshot FOREIGN KEY (id,latest_snapshot_id) REFERENCES product_snapshots(product_id,id);

ALTER TABLE product_snapshot_characters ADD CONSTRAINT uq_snapshot_character_identity UNIQUE (product_snapshot_id,id);

ALTER TABLE product_snapshot_lorebooks ADD CONSTRAINT uq_snapshot_lorebook_identity UNIQUE (product_snapshot_id,id);

ALTER TABLE product_snapshot_lorebooks ADD COLUMN scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all','selected'));

CREATE TABLE product_snapshot_lorebook_characters (
    product_snapshot_id UUID NOT NULL, 
    product_character_id UUID NOT NULL, 
    product_lorebook_id UUID NOT NULL, 
    PRIMARY KEY (product_character_id, product_lorebook_id), 
    FOREIGN KEY(product_snapshot_id, product_character_id) REFERENCES product_snapshot_characters (product_snapshot_id, id) ON DELETE CASCADE, 
    FOREIGN KEY(product_snapshot_id, product_lorebook_id) REFERENCES product_snapshot_lorebooks (product_snapshot_id, id) ON DELETE CASCADE
);

CREATE TABLE product_snapshot_start_sets (
    product_snapshot_id UUID NOT NULL, 
    product_lorebook_id UUID NOT NULL, 
    source_entry_id UUID NOT NULL, 
    title TEXT, 
    content TEXT NOT NULL, 
    sort_order INTEGER NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_snapshot_start_identity UNIQUE (product_snapshot_id, id), 
    CONSTRAINT uq_snapshot_start_entry UNIQUE (product_snapshot_id, source_entry_id), 
    FOREIGN KEY(product_snapshot_id, product_lorebook_id) REFERENCES product_snapshot_lorebooks (product_snapshot_id, id) ON DELETE CASCADE
);


COMMIT;

