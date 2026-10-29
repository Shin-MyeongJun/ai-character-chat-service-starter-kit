"""신고·평가·조치의 HTTP/ORM 독립 공개 값과 업무 오류."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypedDict, TypeVar
from uuid import UUID

# JSONB의 object/array 내부는 legacy 및 향후 증거 키를 포함해 그대로 보존한다.
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]


class LegacyModerationFlag(TypedDict, total=False):
    """0027 이관이 저장하는 과거 검토 출처. 신규 신고에는 키 자체가 없다."""

    id: str
    status: str | None
    reviewed_by: str | None
    reviewed_at: str | None


class ModerationError(Exception):
    """실패 종류를 code로 전달하며 HTTP 표현은 호출 계층에 맡긴다."""

    def __init__(self, code: str) -> None:
        """업무 오류의 안정적인 코드를 저장한다."""
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Cursor:
    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class ActorCommand:
    """인증 경계에서 생성한 행위자 값. 호출자가 직접 인증을 완료해야 한다."""

    user_id: UUID


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageInfo(Generic[T]):
    items: tuple[T, ...]
    next_cursor: Cursor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitReportCommand:
    request_key: UUID
    target_type: str
    target_id: UUID
    reason_code: str
    reason_detail: str | None = None
    target_snapshot_id: UUID | None = None
    occurred_at: datetime | None = None
    form_elapsed_ms: int | None = None
    # 참고 주장만 받는다. 임의 저장소 키나 서버 증거는 입력으로 받지 않는다.
    attachment_claims: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GetReportCommand:
    report_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListReportsCommand:
    limit: int = 30
    cursor: Cursor | None = None
    target_type: str | None = None
    target_id: UUID | None = None
    intake_status: str | None = None
    # pending처럼 보이는 legacy 완료 건을 포함할지 명시적으로 선택한다.
    include_legacy_reviewed: bool = False
    unassessed_only: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangeReportIntakeCommand:
    report_id: UUID
    intake_status: str
    reason: str
    duplicate_of_report_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ReportSummaryInfo:
    id: UUID
    target_type: str
    target_id: UUID
    reason_code: str
    reason_detail: str | None
    received_at: datetime
    intake_status: str
    legacy_review_status: str | None


@dataclass(frozen=True, slots=True)
class ReportInfo:
    id: UUID
    request_key: UUID
    reporter_user_id: UUID | None
    target_type: str
    target_id: UUID
    target_owner_user_id: UUID | None
    target_snapshot_id: UUID | None
    reason_code: str
    reason_detail: str | None
    occurred_at: datetime | None
    received_at: datetime
    form_elapsed_ms: int | None
    evidence_snapshot: JsonObject
    attachment_refs: list[JsonValue]
    evidence_captured_at: datetime | None
    intake_status: str
    duplicate_of_report_id: UUID | None
    intake_reason: str | None


@dataclass(frozen=True, slots=True)
class ReportDisposition:
    report_id: UUID
    disposition: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordAssessmentCommand:
    evaluation_key: str
    target_type: str
    target_id: UUID
    policy_version: str
    outcome: str
    rationale: str
    reports: tuple[ReportDisposition, ...]
    confidence_score: Decimal | None = None
    violation_code: str | None = None
    severity: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    supersedes_assessment_id: UUID | None = None
    # 관리자 관찰이며 검증된 전적을 임의로 받지 않는다.
    reviewer_notes: tuple[str, ...] = ()
    acknowledge_legacy_review: bool = False


@dataclass(frozen=True, slots=True)
class GetAssessmentCommand:
    assessment_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListAssessmentsCommand:
    target_type: str
    target_id: UUID
    limit: int = 30
    cursor: Cursor | None = None


@dataclass(frozen=True, slots=True)
class AssessmentInfo:
    id: UUID
    target_type: str
    target_id: UUID
    assessment_type: str
    evaluator_user_id: UUID | None
    policy_version: str
    evaluated_at: datetime
    window_start: datetime | None
    window_end: datetime | None
    signals: JsonObject
    confidence_score: Decimal | None
    outcome: str
    violation_code: str | None
    severity: int | None
    recommended_actions: list[JsonValue]
    rationale: str
    supersedes_assessment_id: UUID | None
    evaluation_key: str
    reports: tuple[ReportDisposition, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestActionCommand:
    assessment_id: UUID
    target_type: str
    target_id: UUID
    action_type: str
    scope: str
    starts_at: datetime
    idempotency_key: UUID
    ends_at: datetime | None = None
    reverses_action_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class GetActionCommand:
    action_id: UUID


@dataclass(frozen=True, slots=True)
class CancelActionCommand:
    action_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListActionsCommand:
    assessment_id: UUID | None = None
    target_type: str | None = None
    target_id: UUID | None = None
    statuses: tuple[str, ...] = ()
    limit: int = 30
    cursor: Cursor | None = None


@dataclass(frozen=True, slots=True)
class ActionInfo:
    id: UUID
    assessment_id: UUID
    target_type: str
    target_id: UUID
    action_type: str
    scope: str
    starts_at: datetime
    ends_at: datetime | None
    status: str
    idempotency_key: UUID
    domain_action_id: UUID | None
    reverses_action_id: UUID | None
    created_at: datetime
    applied_at: datetime | None
    last_error_code: str | None
