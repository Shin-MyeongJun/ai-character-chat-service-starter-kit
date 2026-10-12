CREATE TABLE tags (
	kind TEXT NOT NULL, 
	name TEXT NOT NULL, 
	description TEXT, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tags_kind CHECK (kind IN ('public', 'internal')), 
	CONSTRAINT ck_tags_name_not_blank CHECK (btrim(name) <> ''), 
	CONSTRAINT uq_tags_kind_name UNIQUE (kind, name), 
	CONSTRAINT uq_tags_identity_kind UNIQUE (id, kind)
);

CREATE TABLE product_tags (
	product_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	tag_kind TEXT DEFAULT 'public' NOT NULL, 
	sort_order INTEGER DEFAULT 0 NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (product_id, tag_id), 
	CONSTRAINT ck_product_tags_kind CHECK (tag_kind = 'public'), 
	CONSTRAINT fk_product_tags_tag_kind FOREIGN KEY(tag_id, tag_kind) REFERENCES tags (id, kind) ON DELETE RESTRICT, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE
);

CREATE INDEX ix_product_tags_tag_product ON product_tags (tag_id, product_id);

CREATE TABLE product_internal_tags (
	product_id UUID NOT NULL, 
	tag_id UUID NOT NULL, 
	tag_kind TEXT DEFAULT 'internal' NOT NULL, 
	source TEXT NOT NULL, 
	assigned_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (product_id, tag_id), 
	CONSTRAINT ck_product_internal_tags_kind CHECK (tag_kind = 'internal'), 
	CONSTRAINT ck_product_internal_tags_source CHECK (source IN ('admin', 'system')), 
	CONSTRAINT fk_product_internal_tags_tag_kind FOREIGN KEY(tag_id, tag_kind) REFERENCES tags (id, kind) ON DELETE RESTRICT, 
	FOREIGN KEY(product_id) REFERENCES products (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_product_internal_tags_tag_product ON product_internal_tags (tag_id, product_id);
