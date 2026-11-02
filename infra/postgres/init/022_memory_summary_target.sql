DO $$ BEGIN
    ALTER TABLE memory_jobs
        ADD COLUMN IF NOT EXISTS summary_through_position BIGINT;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'memory_jobs'::regclass
          AND conname = 'ck_memory_jobs_summary_target'
    ) THEN
        ALTER TABLE memory_jobs ADD CONSTRAINT ck_memory_jobs_summary_target
            CHECK (summary_through_position IS NULL OR summary_through_position > 0);
    END IF;
END $$;
