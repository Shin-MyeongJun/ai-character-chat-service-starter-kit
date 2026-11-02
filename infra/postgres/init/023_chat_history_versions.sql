-- Install atomically while excluding message writes, including legacy writers.
DO $install$
BEGIN
    LOCK TABLE messages IN ACCESS EXCLUSIVE MODE;
    CREATE TABLE IF NOT EXISTS chat_history_versions (
        conversation_id UUID PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
        version BIGINT NOT NULL DEFAULT 0,
        CONSTRAINT ck_chat_history_version CHECK (version >= 0)
    );
    INSERT INTO chat_history_versions (conversation_id)
        SELECT id FROM conversations ON CONFLICT DO NOTHING;

    EXECUTE $ddl$
    CREATE OR REPLACE FUNCTION advance_chat_history_version() RETURNS trigger
    LANGUAGE plpgsql SET search_path FROM CURRENT AS $function$
    BEGIN
        IF TG_OP = 'TRUNCATE' THEN
            UPDATE chat_history_versions SET version = version + 1;
            RETURN NULL;
        END IF;
        IF TG_OP = 'DELETE' THEN
            -- The parent may already be gone during conversation CASCADE.
            UPDATE chat_history_versions SET version = version + 1
                WHERE conversation_id = OLD.conversation_id;
        ELSE
            INSERT INTO chat_history_versions (conversation_id, version)
                VALUES (NEW.conversation_id, 1)
                ON CONFLICT (conversation_id) DO UPDATE
                SET version = chat_history_versions.version + 1;
            IF TG_OP = 'UPDATE' AND OLD.conversation_id <> NEW.conversation_id THEN
                UPDATE chat_history_versions SET version = version + 1
                    WHERE conversation_id = OLD.conversation_id;
            END IF;
        END IF;
        RETURN NULL;
    END
    $function$
    $ddl$;
    DROP TRIGGER IF EXISTS chat_history_changed ON messages;
    CREATE TRIGGER chat_history_changed AFTER INSERT OR UPDATE OR DELETE ON messages
        FOR EACH ROW EXECUTE FUNCTION advance_chat_history_version();
    DROP TRIGGER IF EXISTS chat_history_truncated ON messages;
    CREATE TRIGGER chat_history_truncated AFTER TRUNCATE ON messages
        FOR EACH STATEMENT EXECUTE FUNCTION advance_chat_history_version();
END
$install$;
