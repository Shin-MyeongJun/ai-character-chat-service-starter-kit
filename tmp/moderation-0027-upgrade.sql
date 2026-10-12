BEGIN;

-- Running upgrade 0026 -> 0027

LOCK TABLE moderation_flags IN SHARE MODE;

-- Moderation review schema. Existing flags and audit logs remain unchanged.

CREATE TABLE moderation_reports (
    request_key UUID NOT NULL, 
    reporter_user_id UUID, 
    target_type TEXT NOT NULL, 
    target_id UUID NOT NULL, 
    target_owner_user_id UUID, 
    target_snapshot_id UUID, 
    reason_code TEXT NOT NULL, 
    reason_detail TEXT, 
    occurred_at TIMESTAMP WITH TIME ZONE, 
    received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    form_elapsed_ms BIGINT, 
    evidence_snapshot JSONB DEFAULT '{}'::jsonb NOT NULL, 
    attachment_refs JSONB DEFAULT '[]'::jsonb NOT NULL, 
    evidence_captured_at TIMESTAMP WITH TIME ZONE, 
    intake_status TEXT DEFAULT 'received' NOT NULL, 
    duplicate_of_report_id UUID, 
    intake_reason TEXT, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_moderation_reports_target CHECK (target_type IN ('user','product','character','message')), 
    CONSTRAINT ck_moderation_reports_status CHECK (intake_status IN ('received','duplicate','rejected')), 
    CONSTRAINT ck_moderation_reports_elapsed CHECK (form_elapsed_ms >= 0), 
    CONSTRAINT ck_moderation_reports_evidence CHECK (jsonb_typeof(evidence_snapshot) = 'object'), 
    CONSTRAINT ck_moderation_reports_attachments CHECK (jsonb_typeof(attachment_refs) = 'array'), 
    CONSTRAINT ck_moderation_reports_not_self CHECK (duplicate_of_report_id <> id), 
    CONSTRAINT ck_moderation_reports_duplicate CHECK ((intake_status = 'duplicate') = (duplicate_of_report_id IS NOT NULL)), 
    CONSTRAINT ck_moderation_reports_reason CHECK (length(btrim(reason_code)) > 0), 
    UNIQUE (request_key), 
    FOREIGN KEY(reporter_user_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(duplicate_of_report_id) REFERENCES moderation_reports (id) ON DELETE RESTRICT
);

CREATE INDEX ix_moderation_reports_reporter_received ON moderation_reports (reporter_user_id, received_at);

CREATE INDEX ix_moderation_reports_status_received ON moderation_reports (intake_status, received_at);

CREATE INDEX ix_moderation_reports_target_received ON moderation_reports (target_type, target_id, received_at);

CREATE TABLE moderation_assessments (
    target_type TEXT NOT NULL, 
    target_id UUID NOT NULL, 
    assessment_type TEXT NOT NULL, 
    evaluator_user_id UUID, 
    policy_version TEXT NOT NULL, 
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    window_start TIMESTAMP WITH TIME ZONE, 
    window_end TIMESTAMP WITH TIME ZONE, 
    signals JSONB DEFAULT '{}'::jsonb NOT NULL, 
    confidence_score NUMERIC, 
    outcome TEXT NOT NULL, 
    violation_code TEXT, 
    severity SMALLINT, 
    recommended_actions JSONB DEFAULT '[]'::jsonb NOT NULL, 
    rationale TEXT NOT NULL, 
    supersedes_assessment_id UUID, 
    evaluation_key TEXT NOT NULL, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_moderation_assessments_target CHECK (target_type IN ('user','product','character','message')), 
    CONSTRAINT ck_moderation_assessments_type CHECK (assessment_type IN ('manual','automatic')), 
    CONSTRAINT ck_moderation_assessments_outcome CHECK (outcome IN ('violation','no_violation','insufficient_evidence')), 
    CONSTRAINT ck_moderation_assessments_score CHECK (confidence_score BETWEEN 0 AND 1), 
    CONSTRAINT ck_moderation_assessments_severity CHECK (severity >= 0), 
    CONSTRAINT ck_moderation_assessments_window CHECK ((window_start IS NULL AND window_end IS NULL) OR (window_start IS NOT NULL AND window_end IS NOT NULL AND window_end > window_start)), 
    CONSTRAINT ck_moderation_assessments_signals CHECK (jsonb_typeof(signals) = 'object'), 
    CONSTRAINT ck_moderation_assessments_recommendations CHECK (jsonb_typeof(recommended_actions) = 'array'), 
    CONSTRAINT ck_moderation_assessments_not_self CHECK (supersedes_assessment_id <> id), 
    CONSTRAINT ck_moderation_assessments_required_text CHECK (length(btrim(policy_version)) > 0 AND length(btrim(rationale)) > 0 AND length(btrim(evaluation_key)) > 0), 
    FOREIGN KEY(evaluator_user_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(supersedes_assessment_id) REFERENCES moderation_assessments (id) ON DELETE RESTRICT, 
    UNIQUE (evaluation_key)
);

CREATE INDEX ix_moderation_assessments_supersedes ON moderation_assessments (supersedes_assessment_id);

CREATE INDEX ix_moderation_assessments_target_evaluated ON moderation_assessments (target_type, target_id, evaluated_at);

CREATE TABLE moderation_assessment_reports (
    assessment_id UUID NOT NULL, 
    report_id UUID NOT NULL, 
    disposition TEXT NOT NULL, 
    PRIMARY KEY (assessment_id, report_id), 
    CONSTRAINT ck_moderation_assessment_reports_disposition CHECK (disposition IN ('supported','not_supported','insufficient_evidence','unassessed')), 
    FOREIGN KEY(assessment_id) REFERENCES moderation_assessments (id) ON DELETE RESTRICT, 
    FOREIGN KEY(report_id) REFERENCES moderation_reports (id) ON DELETE RESTRICT
);

CREATE INDEX ix_moderation_assessment_reports_report ON moderation_assessment_reports (report_id);

CREATE TABLE moderation_actions (
    assessment_id UUID NOT NULL, 
    target_type TEXT NOT NULL, 
    target_id UUID NOT NULL, 
    action_type TEXT NOT NULL, 
    scope TEXT NOT NULL, 
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    ends_at TIMESTAMP WITH TIME ZONE, 
    status TEXT DEFAULT 'pending' NOT NULL, 
    idempotency_key UUID NOT NULL, 
    domain_action_id UUID, 
    reverses_action_id UUID, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    applied_at TIMESTAMP WITH TIME ZONE, 
    last_error_code TEXT, 
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_moderation_actions_target CHECK (target_type IN ('user','product','character','message')), 
    CONSTRAINT ck_moderation_actions_type CHECK (action_type IN ('warn','restrict','suspend','ban','revoke')), 
    CONSTRAINT ck_moderation_actions_status CHECK (status IN ('pending','applied','failed','cancelled')), 
    CONSTRAINT ck_moderation_actions_period CHECK (ends_at IS NULL OR ends_at > starts_at), 
    CONSTRAINT ck_moderation_actions_not_self CHECK (reverses_action_id <> id), 
    CONSTRAINT ck_moderation_actions_reversal CHECK ((action_type = 'revoke') = (reverses_action_id IS NOT NULL)), 
    CONSTRAINT ck_moderation_actions_applied CHECK ((status = 'applied') = (applied_at IS NOT NULL)), 
    CONSTRAINT ck_moderation_actions_scope CHECK (length(btrim(scope)) > 0), 
    FOREIGN KEY(assessment_id) REFERENCES moderation_assessments (id) ON DELETE RESTRICT, 
    UNIQUE (idempotency_key), 
    FOREIGN KEY(reverses_action_id) REFERENCES moderation_actions (id) ON DELETE RESTRICT
);

CREATE INDEX ix_moderation_actions_assessment ON moderation_actions (assessment_id);

CREATE INDEX ix_moderation_actions_retry ON moderation_actions (status, created_at) WHERE status IN ('pending','failed');

CREATE INDEX ix_moderation_actions_reverses ON moderation_actions (reverses_action_id);

CREATE INDEX ix_moderation_actions_target_created ON moderation_actions (target_type, target_id, created_at);

-- Legacy review status is provenance, never an inferred violation decision.
INSERT INTO moderation_reports
    (id, request_key, reporter_user_id, target_type, target_id, reason_code,
     reason_detail, received_at, evidence_snapshot)
SELECT id, id, flagged_by, target_type, target_id, 'legacy_unclassified', reason,
       created_at, jsonb_build_object('legacy_moderation_flag', jsonb_build_object(
           'id', id, 'status', status, 'reviewed_by', reviewed_by, 'reviewed_at', reviewed_at))
FROM moderation_flags;

UPDATE alembic_version SET version_num='0027' WHERE alembic_version.version_num = '0026';

COMMIT;

