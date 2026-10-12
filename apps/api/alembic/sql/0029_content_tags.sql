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
