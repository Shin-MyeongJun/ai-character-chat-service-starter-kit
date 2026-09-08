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


COMMIT;

