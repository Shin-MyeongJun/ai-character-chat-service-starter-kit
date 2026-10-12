CREATE TABLE tags (
	name TEXT NOT NULL, 
	description TEXT, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tags_name_not_blank CHECK (btrim(name) <> ''), 
	CONSTRAINT uq_tags_name UNIQUE (name)
);

CREATE TABLE product_tags (
	product_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (product_id, tag_id), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_product_tags_tag_product ON product_tags (tag_id, product_id);

CREATE TABLE product_internal_tags (
	product_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	source TEXT NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (product_id, tag_id), 
	CONSTRAINT ck_product_internal_tags_source CHECK (source IN ('admin', 'system')), 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_product_internal_tags_tag_product ON product_internal_tags (tag_id, product_id);

CREATE TABLE character_tags (
	character_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (character_id, tag_id), 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_character_tags_tag_character ON character_tags (tag_id, character_id);

CREATE TABLE character_internal_tags (
	character_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	source TEXT NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (character_id, tag_id), 
	CONSTRAINT ck_character_internal_tags_source CHECK (source IN ('admin', 'system')), 
	FOREIGN KEY(character_id) REFERENCES characters (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_character_internal_tags_tag_character ON character_internal_tags (tag_id, character_id);

CREATE TABLE lorebook_tags (
	lorebook_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (lorebook_id, tag_id), 
	FOREIGN KEY(lorebook_id) REFERENCES lorebooks (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_lorebook_tags_tag_lorebook ON lorebook_tags (tag_id, lorebook_id);

CREATE TABLE lorebook_internal_tags (
	lorebook_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	source TEXT NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (lorebook_id, tag_id), 
	CONSTRAINT ck_lorebook_internal_tags_source CHECK (source IN ('admin', 'system')), 
	FOREIGN KEY(lorebook_id) REFERENCES lorebooks (id) ON DELETE CASCADE, 
	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE RESTRICT, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_lorebook_internal_tags_tag_lorebook ON lorebook_internal_tags (tag_id, lorebook_id);
