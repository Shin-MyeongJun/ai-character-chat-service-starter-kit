BEGIN;
-- statement
-- Additive wallet rollout. No legacy amounts, keys, states or times are rewritten.
-- Existing rows remain unclassified and the application blocks their activation.
-- Apply in one transaction with legacy writers stopped.
CREATE TABLE credit_wallets (
	user_id UUID NOT NULL,
	currency_code TEXT NOT NULL,
	PRIMARY KEY (user_id, currency_code),
	CONSTRAINT ck_credit_wallets_currency CHECK (currency_code ~ '^[A-Z][A-Z0-9_]{0,31}$'),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT
);
-- statement
CREATE TABLE credit_balances (
	user_id UUID NOT NULL,
	currency_code TEXT NOT NULL,
	bucket TEXT NOT NULL,
	balance BIGINT DEFAULT 0 NOT NULL,
	reserved_credit BIGINT DEFAULT 0 NOT NULL,
	PRIMARY KEY (user_id, currency_code, bucket),
	FOREIGN KEY(user_id, currency_code) REFERENCES credit_wallets (user_id, currency_code) ON DELETE RESTRICT,
	CONSTRAINT ck_credit_balances_bucket CHECK (bucket IN ('free', 'paid')),
	CONSTRAINT ck_credit_balances_amount CHECK (balance >= 0 AND reserved_credit >= 0 AND reserved_credit <= balance)
);
-- statement
ALTER TABLE credit_transactions
ADD COLUMN currency_code text,
ADD COLUMN namespace text,
ADD COLUMN request_key uuid,
ADD COLUMN operation text NOT NULL DEFAULT 'legacy',
DROP CONSTRAINT uq_credit_transactions_idempotency_key;
-- statement
ALTER TABLE credit_reservations
ADD COLUMN currency_code text,
ADD COLUMN free_amount bigint,
ADD COLUMN paid_amount bigint,
ADD COLUMN allocation_status text NOT NULL DEFAULT 'legacy_unknown',
DROP CONSTRAINT uq_credit_reservations_user_request,
DROP CONSTRAINT uq_credit_reservations_settlement,
DROP CONSTRAINT credit_reservations_user_id_fkey;
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT ck_credit_transactions_operation CHECK ((operation = 'legacy' AND currency_code IS NULL AND namespace IS NULL AND request_key IS NULL) OR (operation IN ('grant', 'consume') AND currency_code IS NOT NULL AND namespace IS NOT NULL AND request_key IS NOT NULL));
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT ck_credit_transactions_sign CHECK (operation = 'legacy' OR (operation = 'grant' AND amount > 0) OR (operation = 'consume' AND amount <= 0));
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT uq_credit_transactions_currency_identity UNIQUE (id, user_id, currency_code);
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT uq_credit_transactions_operation UNIQUE (user_id, currency_code, namespace, operation, request_key);
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT uq_credit_transactions_scoped_key UNIQUE (user_id, currency_code, namespace, operation, idempotency_key);
-- statement
CREATE UNIQUE INDEX uq_credit_transactions_idempotency_key ON credit_transactions (idempotency_key) WHERE operation = 'legacy';
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT ck_credit_reservations_allocation CHECK ((allocation_status = 'legacy_unknown' AND currency_code IS NULL AND free_amount IS NULL AND paid_amount IS NULL) OR (allocation_status = 'allocated' AND currency_code IS NOT NULL AND free_amount IS NOT NULL AND paid_amount IS NOT NULL AND free_amount >= 0 AND paid_amount >= 0 AND free_amount::numeric + paid_amount::numeric = reserved_credit));
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT fk_credit_reservations_user FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE RESTRICT;
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT fk_credit_reservations_wallet FOREIGN KEY(user_id, currency_code) REFERENCES credit_wallets (user_id, currency_code) ON DELETE RESTRICT;
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT uq_credit_reservations_settlement UNIQUE (user_id, currency_code, namespace, settlement_key);
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT uq_credit_reservations_user_request UNIQUE (user_id, currency_code, namespace, request_key);
-- statement
CREATE UNIQUE INDEX uq_credit_reservations_legacy_request ON credit_reservations (user_id, namespace, request_key) WHERE currency_code IS NULL;
-- statement
CREATE UNIQUE INDEX uq_credit_reservations_legacy_settlement ON credit_reservations (settlement_key) WHERE currency_code IS NULL;
-- statement
CREATE TABLE credit_transaction_entries (
	transaction_id UUID NOT NULL,
	bucket TEXT NOT NULL,
	user_id UUID NOT NULL,
	currency_code TEXT NOT NULL,
	amount BIGINT NOT NULL,
	PRIMARY KEY (transaction_id, bucket),
	FOREIGN KEY(transaction_id, user_id, currency_code) REFERENCES credit_transactions (id, user_id, currency_code) ON DELETE RESTRICT,
	FOREIGN KEY(user_id, currency_code, bucket) REFERENCES credit_balances (user_id, currency_code, bucket) ON DELETE RESTRICT,
	CONSTRAINT ck_credit_transaction_entries_amount CHECK (amount <> 0)
);
-- statement
ALTER TABLE credit_transactions ADD CONSTRAINT fk_credit_transactions_wallet FOREIGN KEY(user_id, currency_code) REFERENCES credit_wallets (user_id, currency_code) ON DELETE RESTRICT;
-- statement
CREATE INDEX ix_credit_transactions_history ON credit_transactions (user_id, currency_code, created_at, id);
-- statement
ALTER TABLE credit_reservations ADD CONSTRAINT fk_credit_reservations_transaction_currency FOREIGN KEY(transaction_id, user_id, currency_code) REFERENCES credit_transactions (id, user_id, currency_code) ON DELETE RESTRICT;
-- statement
CREATE INDEX ix_credit_reservations_history ON credit_reservations (user_id, currency_code, created_at, id);
-- statement
COMMIT;
