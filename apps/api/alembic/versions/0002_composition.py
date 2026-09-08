from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute(
        "ALTER TABLE product_characters ADD CONSTRAINT uq_product_characters_product_identity UNIQUE (product_id, id)"
    )
    op.execute(
        "ALTER TABLE product_lorebooks ADD CONSTRAINT uq_product_lorebooks_product_identity UNIQUE (product_id, id)"
    )
    op.execute(
        "ALTER TABLE product_lorebooks ADD COLUMN scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all', 'selected'))"
    )
    op.execute("""CREATE TABLE product_lorebook_characters (
        product_id UUID NOT NULL,
        product_character_id UUID NOT NULL,
        product_lorebook_id UUID NOT NULL,
        PRIMARY KEY (product_character_id, product_lorebook_id),
        FOREIGN KEY (product_id, product_character_id) REFERENCES product_characters(product_id, id) ON DELETE CASCADE,
        FOREIGN KEY (product_id, product_lorebook_id) REFERENCES product_lorebooks(product_id, id) ON DELETE CASCADE
    )""")


def downgrade():
    raise RuntimeError("Use a reviewed forward migration or restore a backup.")
