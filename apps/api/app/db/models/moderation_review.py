"""신고 증거, 평가 결과와 적용 이력. 기존 moderation 모델은 호환용으로 유지한다."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.json_types import JsonObject, JsonValue
from app.db.models._mixins import UuidPkMixin


class ModerationReport(UuidPkMixin, Base):
    __tablename__ = "moderation_reports"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user','product','character','message')",
            name="ck_moderation_reports_target",
        ),
        CheckConstraint(
            "intake_status IN ('received','duplicate','rejected')",
            name="ck_moderation_reports_status",
        ),
        CheckConstraint("form_elapsed_ms >= 0", name="ck_moderation_reports_elapsed"),
        CheckConstraint(
            "jsonb_typeof(evidence_snapshot) = 'object'",
            name="ck_moderation_reports_evidence",
        ),
        CheckConstraint(
            "jsonb_typeof(attachment_refs) = 'array'",
            name="ck_moderation_reports_attachments",
        ),
        CheckConstraint(
            "duplicate_of_report_id <> id", name="ck_moderation_reports_not_self"
        ),
        CheckConstraint(
            "(intake_status = 'duplicate') = (duplicate_of_report_id IS NOT NULL)",
            name="ck_moderation_reports_duplicate",
        ),
        CheckConstraint(
            "length(btrim(reason_code)) > 0", name="ck_moderation_reports_reason"
        ),
        Index(
            "ix_moderation_reports_target_received",
            "target_type",
            "target_id",
            "received_at",
        ),
        Index(
            "ix_moderation_reports_reporter_received", "reporter_user_id", "received_at"
        ),
        Index("ix_moderation_reports_status_received", "intake_status", "received_at"),
    )
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    reporter_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    target_owner_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    target_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason_code: Mapped[str] = mapped_column(Text)
    reason_detail: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    form_elapsed_ms: Mapped[int | None] = mapped_column(BigInteger)
    evidence_snapshot: Mapped[JsonObject] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    attachment_refs: Mapped[list[JsonValue]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    evidence_captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    intake_status: Mapped[str] = mapped_column(Text, server_default="received")
    duplicate_of_report_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("moderation_reports.id", ondelete="RESTRICT")
    )
    intake_reason: Mapped[str | None] = mapped_column(Text)


class ModerationAssessment(UuidPkMixin, Base):
    __tablename__ = "moderation_assessments"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user','product','character','message')",
            name="ck_moderation_assessments_target",
        ),
        CheckConstraint(
            "assessment_type IN ('manual','automatic')",
            name="ck_moderation_assessments_type",
        ),
        CheckConstraint(
            "outcome IN ('violation','no_violation','insufficient_evidence')",
            name="ck_moderation_assessments_outcome",
        ),
        CheckConstraint(
            "confidence_score BETWEEN 0 AND 1", name="ck_moderation_assessments_score"
        ),
        CheckConstraint("severity >= 0", name="ck_moderation_assessments_severity"),
        CheckConstraint(
            "(window_start IS NULL AND window_end IS NULL) OR (window_start IS NOT NULL AND window_end IS NOT NULL AND window_end > window_start)",
            name="ck_moderation_assessments_window",
        ),
        CheckConstraint(
            "jsonb_typeof(signals) = 'object'", name="ck_moderation_assessments_signals"
        ),
        CheckConstraint(
            "jsonb_typeof(recommended_actions) = 'array'",
            name="ck_moderation_assessments_recommendations",
        ),
        CheckConstraint(
            "supersedes_assessment_id <> id", name="ck_moderation_assessments_not_self"
        ),
        CheckConstraint(
            "length(btrim(policy_version)) > 0 AND length(btrim(rationale)) > 0 AND length(btrim(evaluation_key)) > 0",
            name="ck_moderation_assessments_required_text",
        ),
        Index(
            "ix_moderation_assessments_target_evaluated",
            "target_type",
            "target_id",
            "evaluated_at",
        ),
        Index("ix_moderation_assessments_supersedes", "supersedes_assessment_id"),
    )
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    assessment_type: Mapped[str] = mapped_column(Text)
    evaluator_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    policy_version: Mapped[str] = mapped_column(Text)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signals: Mapped[JsonObject] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric)
    outcome: Mapped[str] = mapped_column(Text)
    violation_code: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[int | None] = mapped_column(SmallInteger)
    recommended_actions: Mapped[list[JsonValue]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    rationale: Mapped[str] = mapped_column(Text)
    supersedes_assessment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("moderation_assessments.id", ondelete="RESTRICT")
    )
    evaluation_key: Mapped[str] = mapped_column(Text, unique=True)


class ModerationAssessmentReport(Base):
    __tablename__ = "moderation_assessment_reports"
    __table_args__ = (
        CheckConstraint(
            "disposition IN ('supported','not_supported','insufficient_evidence','unassessed')",
            name="ck_moderation_assessment_reports_disposition",
        ),
        Index("ix_moderation_assessment_reports_report", "report_id"),
    )
    assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("moderation_assessments.id", ondelete="RESTRICT"), primary_key=True
    )
    report_id: Mapped[UUID] = mapped_column(
        ForeignKey("moderation_reports.id", ondelete="RESTRICT"), primary_key=True
    )
    disposition: Mapped[str] = mapped_column(Text)


class ModerationAction(UuidPkMixin, Base):
    __tablename__ = "moderation_actions"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('user','product','character','message')",
            name="ck_moderation_actions_target",
        ),
        CheckConstraint(
            "action_type IN ('warn','restrict','suspend','ban','revoke')",
            name="ck_moderation_actions_type",
        ),
        CheckConstraint(
            "status IN ('pending','applied','failed','cancelled')",
            name="ck_moderation_actions_status",
        ),
        CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name="ck_moderation_actions_period",
        ),
        CheckConstraint(
            "reverses_action_id <> id", name="ck_moderation_actions_not_self"
        ),
        CheckConstraint(
            "(action_type = 'revoke') = (reverses_action_id IS NOT NULL)",
            name="ck_moderation_actions_reversal",
        ),
        CheckConstraint(
            "(status = 'applied') = (applied_at IS NOT NULL)",
            name="ck_moderation_actions_applied",
        ),
        CheckConstraint("length(btrim(scope)) > 0", name="ck_moderation_actions_scope"),
        Index("ix_moderation_actions_assessment", "assessment_id"),
        Index(
            "ix_moderation_actions_target_created",
            "target_type",
            "target_id",
            "created_at",
        ),
        Index(
            "ix_moderation_actions_retry",
            "status",
            "created_at",
            postgresql_where=text("status IN ('pending','failed')"),
        ),
        Index("ix_moderation_actions_reverses", "reverses_action_id"),
    )
    assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("moderation_assessments.id", ondelete="RESTRICT")
    )
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    action_type: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    idempotency_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True)
    domain_action_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reverses_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("moderation_actions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
