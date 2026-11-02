-- Apply with API/workers stopped, before starting code that uses recovery admission.
DO $$ BEGIN
ALTER TABLE product_generations
    ADD COLUMN answer_recovery_attempts integer NOT NULL DEFAULT 0,
    ADD COLUMN answer_recovery_next_at timestamptz,
    ADD COLUMN answer_recovery_quarantined_at timestamptz,
    ADD CONSTRAINT ck_answer_recovery_attempts CHECK (answer_recovery_attempts >= 0);

CREATE TABLE answer_recovery_attempts (
    generation_id uuid NOT NULL REFERENCES product_generations(id) ON DELETE CASCADE,
    attempt_count integer NOT NULL,
    started_at timestamptz NOT NULL,
    operator text,
    reason text,
    failure_class text,
    PRIMARY KEY (generation_id, attempt_count),
    CONSTRAINT ck_recovery_attempt_number CHECK (attempt_count > 0),
    CONSTRAINT ck_recovery_operator_reason CHECK (
        (operator IS NULL AND reason IS NULL) OR
        (operator IS NOT NULL AND reason IS NOT NULL AND
         length(trim(operator)) BETWEEN 1 AND 120 AND length(trim(reason)) BETWEEN 1 AND 1000)
    )
);
END $$;
