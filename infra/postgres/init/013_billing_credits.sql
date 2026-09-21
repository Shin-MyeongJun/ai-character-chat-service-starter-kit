-- Reuse the existing held balance and signed movement ledger without rewriting history.
ALTER TABLE credit_accounts ADD COLUMN reserved_credit bigint NOT NULL DEFAULT 0;
ALTER TABLE credit_accounts ADD CONSTRAINT ck_credit_accounts_reserved_credit
    CHECK (reserved_credit >= 0 AND reserved_credit <= balance);

CREATE TABLE credit_reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES credit_accounts(user_id) ON DELETE RESTRICT,
    request_key uuid NOT NULL,
    quote_id uuid NOT NULL REFERENCES billing_quotes(id) ON DELETE RESTRICT,
    status text NOT NULL,
    reserved_credit bigint NOT NULL,
    result_id uuid,
    transaction_id uuid REFERENCES credit_transactions(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL,
    finalized_at timestamptz,
    CONSTRAINT uq_credit_reservations_user_request UNIQUE (user_id, request_key),
    CONSTRAINT uq_credit_reservations_quote UNIQUE (quote_id),
    CONSTRAINT uq_credit_reservations_transaction UNIQUE (transaction_id),
    CONSTRAINT ck_credit_reservations_amount CHECK (reserved_credit >= 0),
    CONSTRAINT ck_credit_reservations_state CHECK (
        (status = 'reserved' AND result_id IS NULL AND transaction_id IS NULL AND finalized_at IS NULL) OR
        (status = 'committed' AND result_id IS NOT NULL AND transaction_id IS NOT NULL AND finalized_at IS NOT NULL) OR
        (status = 'released' AND result_id IS NULL AND transaction_id IS NULL AND finalized_at IS NOT NULL)
    )
);
CREATE INDEX ix_credit_reservations_user_status ON credit_reservations(user_id, status);
