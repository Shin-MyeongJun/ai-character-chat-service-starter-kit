"""Billing quote snapshots, with no production price seed."""

from pathlib import Path

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "infra/postgres/init/012_billing_quotes.sql"
    )
    sql = "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    op.execute(sql)


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM billing_quotes) THEN
            RAISE EXCEPTION 'Billing quotes exist: preserve snapshots before downgrade';
        END IF;
    END $$;""")
    op.drop_table("billing_quotes")
