from alembic import op

revision = "0010"
down_revision = "0008"


def upgrade():
    op.execute(
        "ALTER TABLE conversations ADD COLUMN initial_snapshot_id UUID REFERENCES product_snapshots(id)"
    )
    op.execute(
        "UPDATE conversations SET initial_snapshot_id = product_snapshot_id WHERE product_snapshot_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE conversations DROP CONSTRAINT conversations_product_snapshot_id_start_set_id_fkey"
    )
    op.execute(
        "ALTER TABLE conversations ADD FOREIGN KEY (initial_snapshot_id,start_set_id) REFERENCES product_snapshot_start_sets(product_snapshot_id,id)"
    )
    op.execute(
        "\nCREATE TABLE conversation_version_changes (\n\tconversation_id UUID NOT NULL, \n\tfrom_snapshot_id UUID NOT NULL, \n\tto_snapshot_id UUID NOT NULL, \n\tmode TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_conversation_version_change UNIQUE (conversation_id, to_snapshot_id), \n\tCONSTRAINT ck_conversation_version_change_mode CHECK (mode IN ('automatic','choice')), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(from_snapshot_id) REFERENCES product_snapshots (id), \n\tFOREIGN KEY(to_snapshot_id) REFERENCES product_snapshots (id)\n)\n\n"
    )


def downgrade():
    raise RuntimeError("Preserve transition history; use a forward migration.")
