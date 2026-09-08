from alembic import op
revision='0012'
down_revision='0011'


def upgrade():
    op.execute('ALTER TABLE models ADD COLUMN retirement_announced_at TIMESTAMPTZ, ADD COLUMN shutdown_at TIMESTAMPTZ')
    op.execute('\nCREATE TABLE model_replacements (\n\tproduct_snapshot_id UUID NOT NULL, \n\tfrom_model_id UUID NOT NULL, \n\tto_model_id UUID NOT NULL, \n\treasoning_effort TEXT NOT NULL, \n\teffective_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_model_replacement UNIQUE (product_snapshot_id, from_model_id, to_model_id), \n\tFOREIGN KEY(product_snapshot_id) REFERENCES product_snapshots (id), \n\tFOREIGN KEY(from_model_id) REFERENCES models (id), \n\tFOREIGN KEY(to_model_id) REFERENCES models (id)\n)\n\n')


def downgrade():
    raise RuntimeError('Use a reviewed forward migration.')
