-- Existing histories keep their original messages. New service writes snapshot explicitly.
ALTER TABLE conversations ADD COLUMN opening_mode TEXT NOT NULL DEFAULT 'legacy_messages';
ALTER TABLE conversations ADD CONSTRAINT ck_conversation_opening_mode
    CHECK (opening_mode IN ('legacy_messages', 'snapshot'));
