-- New installations match Alembic 0031; never re-run init SQL on the app DB.
ALTER TABLE memory_jobs ADD COLUMN IF NOT EXISTS claim_token UUID;
