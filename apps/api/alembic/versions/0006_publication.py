from alembic import op
revision = '0006'
down_revision = '0005'


def upgrade():
    op.execute('ALTER TABLE product_snapshots ADD CONSTRAINT uq_product_snapshot_identity UNIQUE (product_id,id)')
    op.execute('ALTER TABLE products ADD COLUMN latest_snapshot_id UUID')
    op.execute('ALTER TABLE products ADD CONSTRAINT fk_product_latest_snapshot FOREIGN KEY (id,latest_snapshot_id) REFERENCES product_snapshots(product_id,id)')
    op.execute('ALTER TABLE product_snapshot_characters ADD CONSTRAINT uq_snapshot_character_identity UNIQUE (product_snapshot_id,id)')
    op.execute('ALTER TABLE product_snapshot_lorebooks ADD CONSTRAINT uq_snapshot_lorebook_identity UNIQUE (product_snapshot_id,id)')
    op.execute("ALTER TABLE product_snapshot_lorebooks ADD COLUMN scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all','selected'))")
    op.execute('\nCREATE TABLE product_snapshot_lorebook_characters (\n\tproduct_snapshot_id UUID NOT NULL, \n\tproduct_character_id UUID NOT NULL, \n\tproduct_lorebook_id UUID NOT NULL, \n\tPRIMARY KEY (product_character_id, product_lorebook_id), \n\tFOREIGN KEY(product_snapshot_id, product_character_id) REFERENCES product_snapshot_characters (product_snapshot_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(product_snapshot_id, product_lorebook_id) REFERENCES product_snapshot_lorebooks (product_snapshot_id, id) ON DELETE CASCADE\n)\n\n')
    op.execute('\nCREATE TABLE product_snapshot_start_sets (\n\tproduct_snapshot_id UUID NOT NULL, \n\tproduct_lorebook_id UUID NOT NULL, \n\tsource_entry_id UUID NOT NULL, \n\ttitle TEXT, \n\tcontent TEXT NOT NULL, \n\tsort_order INTEGER NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_snapshot_start_identity UNIQUE (product_snapshot_id, id), \n\tCONSTRAINT uq_snapshot_start_entry UNIQUE (product_snapshot_id, source_entry_id), \n\tFOREIGN KEY(product_snapshot_id, product_lorebook_id) REFERENCES product_snapshot_lorebooks (product_snapshot_id, id) ON DELETE CASCADE\n)\n\n')


def downgrade():
    raise RuntimeError('Published versions require a reviewed forward migration.')
