"""Add classified currency wallets while retaining unclassified legacy history."""

from pathlib import Path

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "LOCK TABLE credit_accounts, credit_transactions, "
        "credit_reservations IN ACCESS EXCLUSIVE MODE"
    )
    path = (
        Path(__file__).resolve().parents[4]
        / "infra/postgres/init/015_credit_wallets.sql"
    )
    for statement in path.read_text(encoding="utf-8").split("-- statement\n"):
        if statement.strip() and statement.strip() not in {"BEGIN;", "COMMIT;"}:
            op.execute(statement)


def downgrade() -> None:
    # Even empty prepared wallets are durable account state. No lossy downgrade.
    op.execute(
        "LOCK TABLE credit_wallets, credit_balances, credit_transactions, "
        "credit_reservations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM credit_wallets)
          OR EXISTS (SELECT 1 FROM credit_transactions WHERE operation <> 'legacy')
          OR EXISTS (SELECT 1 FROM credit_reservations WHERE currency_code IS NOT NULL)
        THEN
            RAISE EXCEPTION 'Preserve classified credit history before downgrade';
        END IF;
    END $$;""")
    op.execute("DROP TABLE credit_transaction_entries")
    op.execute(
        "ALTER TABLE credit_transactions DROP CONSTRAINT fk_credit_transactions_wallet"
    )
    op.execute(
        "ALTER TABLE credit_reservations DROP CONSTRAINT "
        "fk_credit_reservations_transaction_currency"
    )
    op.execute(
        "ALTER TABLE credit_reservations DROP CONSTRAINT fk_credit_reservations_wallet"
    )
    op.execute("DROP TABLE credit_balances")
    op.execute("DROP TABLE credit_wallets")
    op.execute(
        "ALTER TABLE credit_reservations DROP CONSTRAINT fk_credit_reservations_user"
    )
    op.execute(
        "ALTER TABLE credit_reservations ADD CONSTRAINT "
        "credit_reservations_user_id_fkey FOREIGN KEY (user_id) REFERENCES "
        "credit_accounts(user_id) ON DELETE RESTRICT"
    )
    for column in ("currency_code", "free_amount", "paid_amount", "allocation_status"):
        op.drop_column("credit_reservations", column)
    op.create_unique_constraint(
        "uq_credit_reservations_user_request",
        "credit_reservations",
        ["user_id", "namespace", "request_key"],
    )
    op.create_unique_constraint(
        "uq_credit_reservations_settlement", "credit_reservations", ["settlement_key"]
    )
    op.execute("DROP INDEX uq_credit_transactions_idempotency_key")
    for column in ("currency_code", "namespace", "request_key", "operation"):
        op.drop_column("credit_transactions", column)
    op.create_unique_constraint(
        "uq_credit_transactions_idempotency_key",
        "credit_transactions",
        ["idempotency_key"],
    )
