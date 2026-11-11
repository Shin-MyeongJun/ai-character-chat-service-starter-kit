ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_blocks JSONB;
ALTER TABLE messages ADD CONSTRAINT ck_messages_content_blocks_array
    CHECK (content_blocks IS NULL OR jsonb_typeof(content_blocks) = 'array');
