-- 인증 확장: 기존 식별자·비밀번호·표시명은 보존하며 검증 여부를 임의 추정하지 않는다.
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM users GROUP BY lower(btrim(email)) HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Normalized email collision: resolve legacy accounts before migration';
    END IF;
    IF EXISTS (SELECT 1 FROM users WHERE email ~ '[^ -~]') THEN
        RAISE EXCEPTION 'Normalize legacy international email domains to IDNA before migration';
    END IF;
END $$;
-- statement-break
UPDATE users SET email = lower(btrim(email));
-- statement-break
ALTER TABLE users ADD CONSTRAINT ck_users_email_normalized CHECK (email = lower(btrim(email)));
-- statement-break
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false;
-- statement-break
ALTER TABLE users ADD COLUMN pending_expires_at TIMESTAMPTZ;
-- statement-break
CREATE TABLE auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
-- statement-break
CREATE INDEX ix_auth_sessions_user_id ON auth_sessions(user_id);
-- statement-break
CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions(expires_at);
-- statement-break
CREATE TABLE auth_action_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    purpose TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    CONSTRAINT ck_auth_action_purpose CHECK (purpose IN ('verify', 'reset'))
);
-- statement-break
CREATE INDEX ix_auth_action_tokens_user_id ON auth_action_tokens(user_id);
-- statement-break
CREATE INDEX ix_auth_action_tokens_expires_at ON auth_action_tokens(expires_at);
-- statement-break
CREATE TABLE auth_oauth_attempts (
    state_hash TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
-- statement-break
CREATE INDEX ix_auth_oauth_attempts_expires_at ON auth_oauth_attempts(expires_at);
-- statement-break
CREATE TABLE auth_rate_limits (
    key TEXT PRIMARY KEY,
    count INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
-- statement-break
CREATE INDEX ix_auth_rate_limits_expires_at ON auth_rate_limits(expires_at);
