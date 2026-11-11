"""Account discoveries of stable product image items."""

import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_image_unlocks",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("image_item_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "unlocked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_product_image_unlocks_product_id", "product_image_unlocks", ["product_id"]
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM product_image_unlocks) THEN
                RAISE EXCEPTION 'Product image unlocks exist; downgrade refused';
            END IF;
        END $$;
    """)
    op.drop_table("product_image_unlocks")
