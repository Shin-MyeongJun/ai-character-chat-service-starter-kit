-- Authentication delivery intent. Bearer material is encrypted, never plaintext.
CREATE TABLE auth_mail_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash TEXT NOT NULL UNIQUE REFERENCES auth_action_tokens(token_hash) ON DELETE CASCADE,
    encrypted_token TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT ck_auth_mail_status CHECK (status IN ('pending', 'processing', 'sent', 'cancelled', 'failed')),
    CONSTRAINT ck_auth_mail_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_auth_mail_claim CHECK (
        (status = 'processing' AND claim_token IS NOT NULL AND lease_until IS NOT NULL)
        OR (status <> 'processing' AND claim_token IS NULL AND lease_until IS NULL)
    ),
    CONSTRAINT ck_auth_mail_payload CHECK (
        (status IN ('pending', 'processing') AND encrypted_token IS NOT NULL)
        OR (status IN ('sent', 'cancelled', 'failed') AND encrypted_token IS NULL)
    )
);
CREATE INDEX ix_auth_mail_due ON auth_mail_outbox (status, available_at, id);
CREATE INDEX ix_auth_mail_lease ON auth_mail_outbox (status, lease_until, id);
