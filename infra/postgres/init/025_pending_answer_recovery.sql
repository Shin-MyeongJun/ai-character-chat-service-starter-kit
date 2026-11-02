-- Same index transition as Alembic 0035. Existing generation facts are preserved.
CREATE INDEX ix_generation_pending_answer_lease
    ON product_generations(answer_lease_until)
    WHERE status = 'pending' AND answer_lease_until IS NOT NULL;
DROP INDEX ix_product_generations_answer_lease_until;
