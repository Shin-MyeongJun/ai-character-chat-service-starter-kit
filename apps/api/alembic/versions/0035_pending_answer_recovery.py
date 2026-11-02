"""Keep only leased pending answers in the recovery index."""

from sqlalchemy import text

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Apply with API/workers stopped: ordinary CREATE/DROP INDEX take table locks.
    # Existing terminal leases remain intact; this migration rewrites no facts.
    op.create_index(
        "ix_generation_pending_answer_lease",
        "product_generations",
        ["answer_lease_until"],
        postgresql_where=text("status = 'pending' AND answer_lease_until IS NOT NULL"),
    )
    op.drop_index(
        "ix_product_generations_answer_lease_until", table_name="product_generations"
    )


def downgrade() -> None:
    op.create_index(
        "ix_product_generations_answer_lease_until",
        "product_generations",
        ["answer_lease_until"],
    )
    op.drop_index(
        "ix_generation_pending_answer_lease", table_name="product_generations"
    )
