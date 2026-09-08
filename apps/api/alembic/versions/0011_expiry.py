from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade():
    op.execute(
        "ALTER TABLE product_snapshots ADD COLUMN expires_at TIMESTAMPTZ, ADD COLUMN expiry_reason TEXT"
    )
    op.execute(
        "\nCREATE TABLE product_snapshot_policy_changes (\n\tproduct_snapshot_id UUID NOT NULL, \n\tactor_id UUID, \n\told_expires_at TIMESTAMP WITH TIME ZONE, \n\tnew_expires_at TIMESTAMP WITH TIME ZONE, \n\treason TEXT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(product_snapshot_id) REFERENCES product_snapshots (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id) ON DELETE SET NULL\n)\n\n"
    )


def downgrade():
    raise RuntimeError("Use a forward migration.")
