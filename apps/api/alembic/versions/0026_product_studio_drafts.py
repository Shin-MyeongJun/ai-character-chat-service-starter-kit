"""Store owner-scoped studio documents with optimistic revisions."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_studio_drafts",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.Text(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("publication_digest", sa.Text(), nullable=True),
        sa.Column("publication_release", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_product_studio_drafts_revision"),
    )


def downgrade() -> None:
    op.drop_table("product_studio_drafts")
