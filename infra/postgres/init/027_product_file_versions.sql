DO $$ BEGIN
CREATE TABLE product_file_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    request_id uuid NOT NULL,
    source_media_id uuid,
    storage_kind text NOT NULL,
    storage_id text NOT NULL,
    object_key text NOT NULL,
    content_type text NOT NULL,
    size_bytes bigint NOT NULL,
    original_filename text NOT NULL,
    sha256 text NOT NULL,
    state text NOT NULL,
    awaiting_attachment boolean NOT NULL DEFAULT true,
    unreferenced_since timestamptz,
    CONSTRAINT uq_product_file_request UNIQUE (owner_id, product_id, request_id),
    CONSTRAINT uq_product_file_object UNIQUE (storage_kind, storage_id, object_key),
    CONSTRAINT ck_product_file_state CHECK (state IN ('pending','ready','deleting','deleted')),
    CONSTRAINT ck_product_file_storage CHECK (storage_kind IN ('test_local','s3')),
    CONSTRAINT ck_product_file_size CHECK (size_bytes BETWEEN 1 AND 33554432)
);

CREATE TABLE product_file_references (
    file_version_id uuid NOT NULL REFERENCES product_file_versions(id) ON DELETE RESTRICT,
    kind text NOT NULL,
    reference_id uuid NOT NULL,
    PRIMARY KEY (file_version_id, kind, reference_id),
    CONSTRAINT ck_product_file_reference_kind CHECK (kind IN ('draft','snapshot','staged_answer','opening','message'))
);
END $$;
