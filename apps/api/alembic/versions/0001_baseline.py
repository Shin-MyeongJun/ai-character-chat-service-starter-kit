"""Frozen schema before product implementation.

For existing databases: compare schema and data before explicitly stamping 0001.
Never stamp a database merely because it contains some of these tables.
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    sql = (Path(__file__).parents[1] / "sql/0001_baseline.sql").read_text(
        encoding="utf-8"
    )
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade():
    raise RuntimeError(
        "Destructive baseline downgrade is intentionally disabled; restore a verified backup."
    )
