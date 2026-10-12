CREATE TABLE product_studio_drafts (
    product_id UUID PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CONSTRAINT ck_product_studio_drafts_revision CHECK (revision > 0),
    content_digest TEXT NOT NULL,
    document JSONB NOT NULL,
    publication_digest TEXT,
    publication_release JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
