"""신고자 본인과 관리자의 조회 범위를 분리한다."""

from dataclasses import replace

from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


async def get_own_report(
    session, command: Types.GetReportCommand, *, actor: Types.ActorCommand
) -> Types.ReportSummaryInfo:
    """활성 신고자의 본인 신고만 조회하며 내부 증거·평가·메모를 반환하지 않는다."""
    actor_id = actor.user_id
    await ValidationServiceUtil._require_actor(session, actor_id)
    row = await ReviewRepository.get_report(
        session, command.report_id, reporter_id=actor_id
    )
    info = ValidationServiceUtil.require_info(
        PersistenceMapper.report_entity_to_info(row)
    )
    return PersistenceMapper.report_info_to_summary(info)


async def list_own_reports(
    session, command: Types.ListReportsCommand, *, actor: Types.ActorCommand
) -> Types.PageInfo[Types.ReportSummaryInfo]:
    """신고자 범위를 저장소 쿼리에 적용해 본인 신고의 요약 페이지를 반환한다."""
    actor_id = actor.user_id
    _validate_report_page(command)
    await ValidationServiceUtil._require_actor(session, actor_id)
    row = await ReviewRepository.list_reports(
        session, replace(command, include_legacy_reviewed=True), reporter_id=actor_id
    )
    return PersistenceMapper.reports_row_to_page(row, summary=True)


async def get_admin_report(
    session, command: Types.GetReportCommand, *, actor: Types.ActorCommand
) -> Types.ReportInfo:
    """활성 관리자가 증거와 legacy provenance를 포함한 신고를 조회한다."""
    actor_id = actor.user_id
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.get_report(session, command.report_id)
    return ValidationServiceUtil.require_info(
        PersistenceMapper.report_entity_to_info(row)
    )


async def list_admin_reports(
    session, command: Types.ListReportsCommand, *, actor: Types.ActorCommand
) -> Types.PageInfo[Types.ReportInfo]:
    """관리자가 신고를 커서 조회하며 legacy 완료 건은 기본 대기 목록에서 제외한다."""
    actor_id = actor.user_id
    _validate_report_page(command)
    await ValidationServiceUtil._require_actor(session, actor_id, admin=True)
    row = await ReviewRepository.list_reports(session, command)
    return PersistenceMapper.reports_row_to_page(row)


def _validate_report_page(command):
    """신고 페이지 크기·대상·상태 필터를 검증한다."""
    ValidationServiceUtil.validate_page(command)
    if command.intake_status not in {None, "received", "duplicate", "rejected"}:
        raise Types.ModerationError("invalid_input")
