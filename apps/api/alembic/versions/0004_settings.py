from alembic import op
revision = '0004'
down_revision = '0003'


def upgrade():
    op.execute('ALTER TABLE products ADD COLUMN reasoning_effort TEXT')
    op.execute("ALTER TABLE products ADD COLUMN replacement_policy JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute('ALTER TABLE lorebook_entries ADD CONSTRAINT uq_lorebook_entries_identity UNIQUE (lorebook_id,id)')
    op.execute('''CREATE TABLE product_start_sets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(), product_id UUID NOT NULL,
        lorebook_id UUID NOT NULL, entry_id UUID NOT NULL, sort_order INTEGER NOT NULL,
        UNIQUE (product_id,entry_id),
        FOREIGN KEY (product_id,lorebook_id) REFERENCES product_lorebooks(product_id,lorebook_id) ON DELETE CASCADE,
        FOREIGN KEY (lorebook_id,entry_id) REFERENCES lorebook_entries(lorebook_id,id) ON DELETE CASCADE)''')


def downgrade():
    raise RuntimeError('Use a reviewed forward migration.')
