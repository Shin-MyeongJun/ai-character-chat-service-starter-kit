ALTER TABLE product_generations
    ADD COLUMN answer_metadata JSONB,
    ADD COLUMN answer_lease_until TIMESTAMPTZ;
CREATE INDEX ix_product_generations_answer_lease_until ON product_generations(answer_lease_until);
