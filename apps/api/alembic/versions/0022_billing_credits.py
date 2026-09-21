"""Reuse existing credit ledger and add billing-owned reservations."""

from pathlib import Path

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    path = (
        Path(__file__).resolve().parents[4]
        / "infra/postgres/init/013_billing_credits.sql"
    )
    # Separate statements also support the online asyncpg migration driver.
    sql = "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement.strip())


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM credit_reservations)
            OR EXISTS (SELECT 1 FROM credit_accounts WHERE reserved_credit <> 0) THEN
            RAISE EXCEPTION 'Preserve credit reservation history before downgrade';
        END IF;
    END $$;""")
    op.drop_table("credit_reservations")
    op.drop_constraint(
        "ck_credit_accounts_reserved_credit", "credit_accounts", type_="check"
    )
    op.drop_column("credit_accounts", "reserved_credit")
