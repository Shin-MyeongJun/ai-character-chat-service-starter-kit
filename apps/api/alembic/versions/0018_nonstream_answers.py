"""Durable answer metadata and recovery lease; legacy generations remain valid."""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE product_generations ADD COLUMN answer_metadata JSONB, ADD COLUMN answer_lease_until TIMESTAMPTZ"
    )
    op.create_index(
        "ix_product_generations_answer_lease_until",
        "product_generations",
        ["answer_lease_until"],
    )


def downgrade():
    op.drop_index(
        "ix_product_generations_answer_lease_until", table_name="product_generations"
    )
    op.execute(
        "ALTER TABLE product_generations DROP COLUMN answer_lease_until, DROP COLUMN answer_metadata"
    )
