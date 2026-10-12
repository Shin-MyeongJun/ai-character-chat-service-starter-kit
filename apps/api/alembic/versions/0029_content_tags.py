"""Share the tag dictionary across public/internal content associations."""

from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "character_tags",
    "character_internal_tags",
    "lorebook_tags",
    "lorebook_internal_tags",
)


def upgrade() -> None:
    op.execute(
        "LOCK TABLE tags, product_tags, product_internal_tags IN ACCESS EXCLUSIVE MODE"
    )
    # Preserve distinct legacy IDs/metadata rather than silently merging by name.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT name FROM tags GROUP BY name HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'Duplicate tag names across kinds; resolve names and associations before upgrade';
        END IF;
    END $$;""")
    for table, fk, check in (
        ("product_tags", "fk_product_tags_tag_kind", "ck_product_tags_kind"),
        (
            "product_internal_tags",
            "fk_product_internal_tags_tag_kind",
            "ck_product_internal_tags_kind",
        ),
    ):
        op.drop_constraint(fk, table, type_="foreignkey")
        op.drop_constraint(check, table, type_="check")
        op.drop_column(table, "tag_kind")
        op.create_foreign_key(
            f"fk_{table}_tag", table, "tags", ["tag_id"], ["id"], ondelete="RESTRICT"
        )
    op.drop_constraint("uq_tags_kind_name", "tags", type_="unique")
    op.drop_constraint("uq_tags_identity_kind", "tags", type_="unique")
    op.drop_constraint("ck_tags_kind", "tags", type_="check")
    op.drop_column("tags", "kind")
    op.create_unique_constraint("uq_tags_name", "tags", ["name"])
    op.add_column(
        "product_tags",
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_product_tags_assigned_by",
        "product_tags",
        "users",
        ["assigned_by"],
        ["id"],
        ondelete="SET NULL",
    )
    path = Path(__file__).resolve().parents[1] / "sql/0029_content_tags.sql"
    for statement in path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    tables = ("tags", "product_tags", "product_internal_tags", *NEW_TABLES)
    op.execute("LOCK TABLE " + ", ".join(tables) + " IN ACCESS EXCLUSIVE MODE")
    # Original public/internal dictionary membership cannot be reconstructed.
    conditions = " OR ".join(f"EXISTS (SELECT 1 FROM {table})" for table in tables)
    op.execute(f"""DO $$ BEGIN
        IF {conditions} THEN
            RAISE EXCEPTION 'Content tag data exists; preserve it before downgrade';
        END IF;
    END $$;""")
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    op.drop_constraint(
        "fk_product_tags_assigned_by", "product_tags", type_="foreignkey"
    )
    op.drop_column("product_tags", "assigned_by")
    op.drop_constraint("uq_tags_name", "tags", type_="unique")
    op.add_column("tags", sa.Column("kind", sa.Text(), nullable=False))
    op.create_check_constraint("ck_tags_kind", "tags", "kind IN ('public', 'internal')")
    op.create_unique_constraint("uq_tags_kind_name", "tags", ["kind", "name"])
    op.create_unique_constraint("uq_tags_identity_kind", "tags", ["id", "kind"])
    for table, kind in (
        ("product_tags", "public"),
        ("product_internal_tags", "internal"),
    ):
        op.drop_constraint(f"fk_{table}_tag", table, type_="foreignkey")
        op.add_column(
            table, sa.Column("tag_kind", sa.Text(), nullable=False, server_default=kind)
        )
        op.create_check_constraint(f"ck_{table}_kind", table, f"tag_kind = '{kind}'")
        op.create_foreign_key(
            f"fk_{table}_tag_kind",
            table,
            "tags",
            ["tag_id", "tag_kind"],
            ["id", "kind"],
            ondelete="RESTRICT",
        )
