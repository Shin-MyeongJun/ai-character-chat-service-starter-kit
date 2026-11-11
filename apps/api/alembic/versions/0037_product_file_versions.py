"""Private product file versions and retention references."""

from pathlib import Path

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).parents[1] / "sql/0037_product_file_versions.sql").read_text(
            encoding="utf-8"
        )
    )


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM product_file_versions) THEN
                RAISE EXCEPTION 'Product file versions exist; downgrade refused';
            END IF;
        END $$;
    """)
    op.drop_table("product_file_references")
    op.drop_table("product_file_versions")
