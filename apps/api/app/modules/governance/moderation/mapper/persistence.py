"""이미 받은 신고·평가·조치를 공개 값으로 변환한다. DB 조회는 없다."""

from copy import deepcopy
from typing import Literal, TypeVar, cast, overload
from uuid import UUID

from app.db.models.moderation_review import ModerationAction, ModerationReport
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.repository import review as ReviewRepository

T = TypeVar("T", bound=UUID | None)


@overload
def report_entity_to_info(entity: ModerationReport) -> Types.ReportInfo: ...


@overload
def report_entity_to_info(entity: None) -> None: ...


def report_entity_to_info(
    entity: ModerationReport | None,
) -> Types.ReportInfo | None:
    """신고 Entity와 JSON을 독립적인 관리자용 Info로 복사한다."""
    if entity is None:
        return None
    # JSONB 디코딩 결과 및 ck_moderation_reports_evidence/attachments의
    # object/array 제약이 근거다. 내부 legacy 키는 검열하거나 정규화하지 않는다.
    return Types.ReportInfo(
        id=entity.id,
        request_key=entity.request_key,
        reporter_user_id=entity.reporter_user_id,
        target_type=entity.target_type,
        target_id=entity.target_id,
        target_owner_user_id=entity.target_owner_user_id,
        target_snapshot_id=entity.target_snapshot_id,
        reason_code=entity.reason_code,
        reason_detail=entity.reason_detail,
        occurred_at=entity.occurred_at,
        received_at=entity.received_at,
        form_elapsed_ms=entity.form_elapsed_ms,
        evidence_snapshot=deepcopy(cast(Types.JsonObject, entity.evidence_snapshot)),
        attachment_refs=deepcopy(cast(list[Types.JsonValue], entity.attachment_refs)),
        evidence_captured_at=entity.evidence_captured_at,
        intake_status=entity.intake_status,
        duplicate_of_report_id=entity.duplicate_of_report_id,
        intake_reason=entity.intake_reason,
    )


def report_info_to_summary(info: Types.ReportInfo) -> Types.ReportSummaryInfo:
    """신고자에게 허용된 접수 정보만 선택해 내부 증거와 메모를 제외한다."""
    # 0027의 jsonb_build_object는 legacy status를 문자열로 보존한다.
    # 누락 시 {} 기본값을 사용하며 명시적 null/손상 값을 보정하지 않는다.
    legacy = cast(
        Types.LegacyModerationFlag,
        info.evidence_snapshot.get("legacy_moderation_flag", {}),
    )
    return Types.ReportSummaryInfo(
        id=info.id,
        target_type=info.target_type,
        target_id=info.target_id,
        reason_code=info.reason_code,
        reason_detail=info.reason_detail,
        received_at=info.received_at,
        intake_status=info.intake_status,
        legacy_review_status=legacy.get("status"),
    )


@overload
def assessment_row_to_info(
    row: ReviewRepository.AssessmentRow,
) -> Types.AssessmentInfo: ...


@overload
def assessment_row_to_info(row: None) -> None: ...


def assessment_row_to_info(
    row: ReviewRepository.AssessmentRow | None,
) -> Types.AssessmentInfo | None:
    """평가 raw 묶음과 근거 연결을 lazy 조회 없이 공개 값으로 변환한다."""
    if row is None:
        return None
    entity = row.entity
    # JSONB 디코딩 및 assessments의 signals object/recommendations array
    # 제약을 신뢰한다. 중첩 JSON은 그대로 깊은 복사한다.
    return Types.AssessmentInfo(
        id=entity.id,
        target_type=entity.target_type,
        target_id=entity.target_id,
        assessment_type=entity.assessment_type,
        evaluator_user_id=entity.evaluator_user_id,
        policy_version=entity.policy_version,
        evaluated_at=entity.evaluated_at,
        window_start=entity.window_start,
        window_end=entity.window_end,
        signals=deepcopy(cast(Types.JsonObject, entity.signals)),
        confidence_score=entity.confidence_score,
        outcome=entity.outcome,
        violation_code=entity.violation_code,
        severity=entity.severity,
        recommended_actions=deepcopy(
            cast(list[Types.JsonValue], entity.recommended_actions)
        ),
        rationale=entity.rationale,
        supersedes_assessment_id=entity.supersedes_assessment_id,
        evaluation_key=entity.evaluation_key,
        reports=tuple(
            sorted(
                (
                    Types.ReportDisposition(link.report_id, link.disposition)
                    for link in row.reports
                ),
                key=lambda item: str(item.report_id),
            )
        ),
    )


@overload
def action_entity_to_info(entity: ModerationAction) -> Types.ActionInfo: ...


@overload
def action_entity_to_info(entity: None) -> None: ...


def action_entity_to_info(entity: ModerationAction | None) -> Types.ActionInfo | None:
    """조치 Entity를 분리된 적용 결과 Info로 변환한다."""
    if entity is None:
        return None
    return Types.ActionInfo(
        id=entity.id,
        assessment_id=entity.assessment_id,
        target_type=entity.target_type,
        target_id=entity.target_id,
        action_type=entity.action_type,
        scope=entity.scope,
        starts_at=entity.starts_at,
        ends_at=entity.ends_at,
        status=entity.status,
        idempotency_key=entity.idempotency_key,
        domain_action_id=entity.domain_action_id,
        reverses_action_id=entity.reverses_action_id,
        created_at=entity.created_at,
        applied_at=entity.applied_at,
        last_error_code=entity.last_error_code,
    )


def scalar_row_to_value(value: T) -> T:
    """저장소가 조회한 선택적 이력 UUID를 업무 계층의 값으로 전달한다."""
    return value


@overload
def reports_row_to_page(
    row: ReviewRepository.PageRow[ModerationReport], *, summary: Literal[True]
) -> Types.PageInfo[Types.ReportSummaryInfo]: ...


@overload
def reports_row_to_page(
    row: ReviewRepository.PageRow[ModerationReport], *, summary: Literal[False] = False
) -> Types.PageInfo[Types.ReportInfo]: ...


@overload
def reports_row_to_page(
    row: ReviewRepository.PageRow[ModerationReport], *, summary: bool
) -> Types.PageInfo[Types.ReportSummaryInfo] | Types.PageInfo[Types.ReportInfo]: ...


def reports_row_to_page(
    row: ReviewRepository.PageRow[ModerationReport], *, summary: bool = False
) -> Types.PageInfo[Types.ReportSummaryInfo] | Types.PageInfo[Types.ReportInfo]:
    """신고 페이지를 관리자용 또는 신고자용 값 페이지로 변환한다."""
    items = tuple(report_entity_to_info(item) for item in row.items)
    if summary:
        return Types.PageInfo(
            tuple(report_info_to_summary(item) for item in items), row.next_cursor
        )
    return Types.PageInfo(items, row.next_cursor)


def assessments_row_to_page(
    row: ReviewRepository.PageRow[ReviewRepository.AssessmentRow],
) -> Types.PageInfo[Types.AssessmentInfo]:
    """평가 raw 페이지를 공개 평가 페이지로 변환한다."""
    return Types.PageInfo(
        tuple(assessment_row_to_info(item) for item in row.items), row.next_cursor
    )


def actions_row_to_page(
    row: ReviewRepository.PageRow[ModerationAction],
) -> Types.PageInfo[Types.ActionInfo]:
    """조치 raw 페이지를 공개 조치 페이지로 변환한다."""
    return Types.PageInfo(
        tuple(action_entity_to_info(item) for item in row.items), row.next_cursor
    )
