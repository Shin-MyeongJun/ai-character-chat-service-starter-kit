-- Additive managed media references. Legacy URL columns are unchanged.
CREATE TABLE character_media (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL,
    character_id UUID NOT NULL,
    request_id UUID NOT NULL,
    storage_kind TEXT NOT NULL,
    storage_id TEXT NOT NULL,
    object_key TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    original_filename TEXT NOT NULL,
    purpose TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    binding TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_character_media_request UNIQUE (owner_id, character_id, request_id),
    CONSTRAINT uq_character_media_object UNIQUE (storage_kind, storage_id, object_key),
    CONSTRAINT ck_character_media_state CHECK (state IN ('pending','ready','deleting','deleted')),
    CONSTRAINT ck_character_media_size CHECK (size_bytes >= 0),
    CONSTRAINT ck_character_media_storage CHECK (storage_kind IN ('test_local','s3'))
);
ALTER TABLE character_images ADD COLUMN media_id UUID REFERENCES character_media(id) ON DELETE RESTRICT;
CREATE INDEX ix_character_images_media_id ON character_images(media_id);
ALTER TABLE character_assets ADD COLUMN media_id UUID REFERENCES character_media(id) ON DELETE RESTRICT;
CREATE INDEX ix_character_assets_media_id ON character_assets(media_id);
ALTER TABLE character_snapshot_images ADD COLUMN media_id UUID REFERENCES character_media(id) ON DELETE RESTRICT;
CREATE INDEX ix_character_snapshot_images_media_id ON character_snapshot_images(media_id);
ALTER TABLE character_snapshot_assets ADD COLUMN media_id UUID REFERENCES character_media(id) ON DELETE RESTRICT;
CREATE INDEX ix_character_snapshot_assets_media_id ON character_snapshot_assets(media_id);
