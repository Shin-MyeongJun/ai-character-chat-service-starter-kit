from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    op.execute(
        "ALTER TABLE conversations ADD COLUMN product_snapshot_id UUID, ADD COLUMN start_set_id UUID"
    )
    op.execute(
        "ALTER TABLE conversations ADD FOREIGN KEY (product_id,product_snapshot_id) REFERENCES product_snapshots(product_id,id), ADD FOREIGN KEY (product_snapshot_id,start_set_id) REFERENCES product_snapshot_start_sets(product_snapshot_id,id)"
    )
    op.execute(
        "ALTER TABLE conversation_characters ADD COLUMN product_character_id UUID REFERENCES product_snapshot_characters(id), ALTER COLUMN character_id DROP NOT NULL"
    )
    # Baseline and init SQL use PostgreSQL-generated names for these FKs.
    op.execute(
        "ALTER TABLE conversation_characters DROP CONSTRAINT conversation_characters_character_id_fkey"
    )
    op.execute(
        "ALTER TABLE conversation_characters ADD FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE SET NULL, ADD CONSTRAINT uq_conversation_snapshot_character UNIQUE (conversation_id,product_character_id)"
    )
    op.execute(
        "ALTER TABLE messages ADD COLUMN product_snapshot_id UUID REFERENCES product_snapshots(id), ADD COLUMN product_character_id UUID"
    )
    op.execute(
        "ALTER TABLE messages ADD FOREIGN KEY (product_snapshot_id,product_character_id) REFERENCES product_snapshot_characters(product_snapshot_id,id)"
    )
    op.execute(
        "ALTER TABLE messages DROP CONSTRAINT ck_messages_character_sender_has_character"
    )
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_character_sender_has_character CHECK (product_snapshot_id IS NULL OR sender_type <> 'character' OR product_character_id IS NOT NULL)"
    )


def downgrade():
    raise RuntimeError(
        "Conversation history must be preserved; use a reviewed forward migration."
    )
