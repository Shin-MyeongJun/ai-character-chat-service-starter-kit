"""이미 받은 신고·평가·조치를 공개 값으로 변환한다. DB 조회는 없다."""

from copy import deepcopy
from dataclasses import fields

from app.modules.governance.moderation import types as Types


def report_entity_to_info(entity) -> Types.ReportInfo | None:
    """신고 Entity와 JSON을 독립적인 관리자용 Info로 복사한다."""
    return (
        None
        if entity is None
        else Types.ReportInfo(
            **{
                f.name: deepcopy(getattr(entity, f.name))
                for f in fields(Types.ReportInfo)
            }
        )
    )


def report_info_to_summary(info: Types.ReportInfo) -> Types.ReportSummaryInfo:
    """신고자에게 허용된 접수 정보만 선택해 내부 증거와 메모를 제외한다."""
    values = {
        f.name: getattr(info, f.name)
        for f in fields(Types.ReportSummaryInfo)
        if f.name != "legacy_review_status"
    }
    values["legacy_review_status"] = info.evidence_snapshot.get(
        "legacy_moderation_flag", {}
    ).get("status")
    return Types.ReportSummaryInfo(**values)


def assessment_row_to_info(row) -> Types.AssessmentInfo | None:
    """평가 raw 묶음과 근거 연결을 lazy 조회 없이 공개 값으로 변환한다."""
    if row is None:
        return None
    values = {
        f.name: deepcopy(getattr(row.entity, f.name))
        for f in fields(Types.AssessmentInfo)
        if f.name != "reports"
    }
    values["reports"] = tuple(
        sorted(
            (
                Types.ReportDisposition(link.report_id, link.disposition)
                for link in row.reports
            ),
            key=lambda item: str(item.report_id),
        )
    )
    return Types.AssessmentInfo(**values)


def action_entity_to_info(entity) -> Types.ActionInfo | None:
    """조치 Entity를 분리된 적용 결과 Info로 변환한다."""
    return (
        None
        if entity is None
        else Types.ActionInfo(
            **{
                f.name: deepcopy(getattr(entity, f.name))
                for f in fields(Types.ActionInfo)
            }
        )
    )


def scalar_row_to_value(value):
    """저장소 스칼라를 업무 계층의 값으로 전달한다."""
    return value


def reports_row_to_page(row, *, summary=False) -> Types.PageInfo:
    """신고 페이지를 관리자용 또는 신고자용 값 페이지로 변환한다."""
    items = tuple(report_entity_to_info(item) for item in row.items)
    return Types.PageInfo(
        tuple(report_info_to_summary(item) for item in items) if summary else items,
        row.next_cursor,
    )


def assessments_row_to_page(row) -> Types.PageInfo[Types.AssessmentInfo]:
    """평가 raw 페이지를 공개 평가 페이지로 변환한다."""
    return Types.PageInfo(
        tuple(assessment_row_to_info(item) for item in row.items), row.next_cursor
    )


def actions_row_to_page(row) -> Types.PageInfo[Types.ActionInfo]:
    """조치 raw 페이지를 공개 조치 페이지로 변환한다."""
    return Types.PageInfo(
        tuple(action_entity_to_info(item) for item in row.items), row.next_cursor
    )
