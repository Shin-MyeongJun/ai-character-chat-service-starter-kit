from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.execute(
        "\nCREATE TABLE product_release_notes (\n\tproduct_snapshot_id UUID NOT NULL, \n\tsummary TEXT NOT NULL, \n\tbody TEXT NOT NULL, \n\tchange_kind TEXT NOT NULL, \n\tupdate_policy TEXT NOT NULL, \n\tcorrected_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (product_snapshot_id), \n\tCONSTRAINT ck_release_kind CHECK (change_kind IN ('initial','media','content')), \n\tCONSTRAINT ck_release_policy CHECK (update_policy IN ('automatic','choice')), \n\tCONSTRAINT ck_release_content_choice CHECK (change_kind = 'media' OR update_policy = 'choice'), \n\tFOREIGN KEY(product_snapshot_id) REFERENCES product_snapshots (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE product_release_note_revisions (\n\tproduct_snapshot_id UUID NOT NULL, \n\teditor_id UUID, \n\tprevious_summary TEXT NOT NULL, \n\tprevious_body TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(product_snapshot_id) REFERENCES product_release_notes (product_snapshot_id) ON DELETE CASCADE, \n\tFOREIGN KEY(editor_id) REFERENCES users (id) ON DELETE SET NULL\n)\n\n"
    )


def downgrade():
    raise RuntimeError("Use a reviewed forward migration.")
