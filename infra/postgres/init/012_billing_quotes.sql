-- Billing owns immutable request/price snapshots. Decimal values are JSON strings.
CREATE TABLE billing_quotes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    request_key uuid NOT NULL,
    request_snapshot jsonb NOT NULL,
    price_snapshot jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    CONSTRAINT uq_billing_quotes_user_request UNIQUE (user_id, request_key),
    CONSTRAINT ck_billing_quotes_expiration CHECK (expires_at > created_at),
    CONSTRAINT ck_billing_quotes_snapshots CHECK (
        jsonb_typeof(request_snapshot) = 'object' AND jsonb_typeof(price_snapshot) = 'object'
    )
);
