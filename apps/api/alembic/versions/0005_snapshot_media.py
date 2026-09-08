from alembic import op
revision = '0005'
down_revision = '0004'


def upgrade():
    op.execute('\nCREATE TABLE character_snapshot_images (\n\tcharacter_snapshot_id UUID NOT NULL, \n\tsource_image_id UUID NOT NULL, \n\temotion_tag TEXT NOT NULL, \n\timage_url TEXT NOT NULL, \n\tis_default BOOLEAN NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_snapshot_image_emotion UNIQUE (character_snapshot_id, emotion_tag), \n\tFOREIGN KEY(character_snapshot_id) REFERENCES character_snapshots (id) ON DELETE CASCADE\n)\n\n')
    op.execute('CREATE UNIQUE INDEX uq_snapshot_image_default ON character_snapshot_images (character_snapshot_id) WHERE is_default = true')
    op.execute("\nCREATE TABLE character_snapshot_assets (\n\tcharacter_snapshot_id UUID NOT NULL, \n\tsource_asset_id UUID NOT NULL, \n\tasset_type TEXT NOT NULL, \n\tpurpose TEXT NOT NULL, \n\tfile_url TEXT NOT NULL, \n\tid UUID DEFAULT gen_random_uuid() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_snapshot_asset_type CHECK (asset_type IN ('image','audio','video')), \n\tFOREIGN KEY(character_snapshot_id) REFERENCES character_snapshots (id) ON DELETE CASCADE\n)\n\n")
    op.execute('CREATE INDEX ix_snapshot_assets_parent ON character_snapshot_assets (character_snapshot_id)')


def downgrade():
    raise RuntimeError('Snapshot media retention forbids automatic destructive downgrade.')
