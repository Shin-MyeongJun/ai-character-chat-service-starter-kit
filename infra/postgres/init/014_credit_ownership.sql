-- Single-balance ownership split. Run while old application writers are stopped.
-- Statements are delimited for Alembic's asyncpg driver, including DO blocks.
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM credit_reservations r
        JOIN credit_transactions t ON t.id = r.transaction_id
        WHERE t.user_id <> r.user_id OR t.amount <> -r.reserved_credit
            OR t.reference_id IS DISTINCT FROM r.result_id
    ) THEN
        RAISE EXCEPTION 'Inconsistent credit settlement history; ownership migration aborted';
    END IF;
    IF EXISTS (
        SELECT 1 FROM credit_reservations r JOIN credit_transactions t
        ON t.idempotency_key = 'billing:credit-settlement:' || r.user_id::text || ':' || r.request_key::text
        WHERE r.status <> 'committed'
    ) THEN
        RAISE EXCEPTION 'Conflicting credit settlement key; ownership migration aborted';
    END IF;
END $$;
-- statement
ALTER TABLE credit_reservations
    ADD COLUMN namespace text,
    ADD COLUMN reference_id uuid,
    ADD COLUMN reason text,
    ADD COLUMN settlement_key text;
-- statement
UPDATE credit_reservations r SET
    namespace = 'billing',
    reference_id = r.id,
    reason = COALESCE((SELECT t.reason FROM credit_transactions t WHERE t.id = r.transaction_id), 'chat_usage'),
    settlement_key = COALESCE(
        (SELECT t.idempotency_key FROM credit_transactions t WHERE t.id = r.transaction_id),
        'billing:credit-settlement:' || r.user_id::text || ':' || r.request_key::text
    );
-- statement
ALTER TABLE credit_reservations
    ALTER COLUMN namespace SET NOT NULL,
    ALTER COLUMN reference_id SET NOT NULL,
    ALTER COLUMN reason SET NOT NULL,
    ALTER COLUMN settlement_key SET NOT NULL,
    ADD CONSTRAINT uq_credit_reservations_settlement UNIQUE (settlement_key),
    ADD CONSTRAINT uq_credit_reservations_identity UNIQUE (id, user_id, request_key);
-- statement
ALTER TABLE billing_quotes ADD CONSTRAINT uq_billing_quotes_identity UNIQUE (id, user_id, request_key);
-- statement
CREATE TABLE billing_credit_bindings (
    reservation_id uuid PRIMARY KEY,
    quote_id uuid NOT NULL,
    user_id uuid NOT NULL,
    request_key uuid NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_billing_credit_bindings_quote UNIQUE (quote_id),
    CONSTRAINT uq_billing_credit_bindings_user_request UNIQUE (user_id, request_key),
    FOREIGN KEY (reservation_id, user_id, request_key)
        REFERENCES credit_reservations (id, user_id, request_key) ON DELETE RESTRICT,
    FOREIGN KEY (quote_id, user_id, request_key)
        REFERENCES billing_quotes (id, user_id, request_key) ON DELETE RESTRICT
);
-- statement
INSERT INTO billing_credit_bindings (reservation_id, quote_id, user_id, request_key, created_at)
SELECT id, quote_id, user_id, request_key, created_at FROM credit_reservations;
-- statement
ALTER TABLE credit_reservations DROP COLUMN quote_id;
-- statement
ALTER TABLE credit_reservations DROP CONSTRAINT uq_credit_reservations_user_request;
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT uq_credit_reservations_user_request UNIQUE (user_id, namespace, request_key);
-- statement
-- Reason is an opaque caller-owned value. Historical values are never rewritten.
ALTER TABLE credit_transactions DROP CONSTRAINT ck_credit_transactions_reason;
