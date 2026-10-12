"""Add a reusable tag dictionary and current product tag associations."""

from pathlib import Path

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = Path(__file__).resolve().parents[1] / "sql/0028_tags.sql"
    for statement in path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    op.execute(
        "LOCK TABLE tags, product_tags, product_internal_tags IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM tags)
        OR EXISTS (SELECT 1 FROM product_tags)
        OR EXISTS (SELECT 1 FROM product_internal_tags) THEN
            RAISE EXCEPTION 'Tag data exists; preserve it before downgrade';
        END IF;
    END $$;""")
    op.drop_table("product_internal_tags")
    op.drop_table("product_tags")
    op.drop_table("tags")
