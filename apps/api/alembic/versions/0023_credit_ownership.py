"""Separate credit persistence from billing, retaining the single balance."""

from pathlib import Path

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        (
            "LOCK TABLE credit_accounts, credit_transactions, "
            "credit_reservations, billing_quotes IN ACCESS EXCLUSIVE MODE"
        )
    )
    path = (
        Path(__file__).resolve().parents[4]
        / "infra/postgres/init/014_credit_ownership.sql"
    )
    for statement in path.read_text(encoding="utf-8").split("-- statement\n"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    # Never erase bindings or opaque metadata from a live reservation history.
    op.execute(
        (
            "DO $$ BEGIN\n"
            "        IF EXISTS (SELECT 1 FROM credit_reservations)\n"
            "            OR EXISTS (SELECT 1 FROM billing_credit_bindings)\n"
            "            OR EXISTS (SELECT 1 FROM credit_transactions\n"
            "                WHERE reason NOT IN ('chat_usage', "
            "'purchase', 'refund', 'subscription_grant')) THEN\n"
            "            RAISE EXCEPTION 'Preserve credit ownership "
            "history before downgrade';\n"
            "        END IF;\n"
            "    END $$;"
        )
    )
    op.drop_table("billing_credit_bindings")
    op.drop_constraint("uq_billing_quotes_identity", "billing_quotes", type_="unique")
    op.execute(
        (
            "ALTER TABLE credit_reservations ADD COLUMN quote_id uuid NOT "
            "NULL REFERENCES billing_quotes(id) ON DELETE RESTRICT"
        )
    )
    op.create_unique_constraint(
        "uq_credit_reservations_quote", "credit_reservations", ["quote_id"]
    )
    op.drop_constraint(
        "uq_credit_reservations_user_request", "credit_reservations", type_="unique"
    )
    op.create_unique_constraint(
        "uq_credit_reservations_user_request",
        "credit_reservations",
        ["user_id", "request_key"],
    )
    op.drop_constraint(
        "uq_credit_reservations_identity", "credit_reservations", type_="unique"
    )
    for column in ("namespace", "reference_id", "reason", "settlement_key"):
        op.drop_column("credit_reservations", column)
    op.create_check_constraint(
        "ck_credit_transactions_reason",
        "credit_transactions",
        "reason IN ('chat_usage', 'purchase', 'refund', 'subscription_grant')",
    )
