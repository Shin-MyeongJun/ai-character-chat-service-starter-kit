"""신고·평가·조치 저장과 잠금. 업무 판단과 트랜잭션 종료는 수행하지 않는다."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select, update

from app.db.models.moderation import AuditLog
from app.db.models.moderation_review import (
    ModerationAction,
    ModerationAssessment,
    ModerationAssessmentReport,
    ModerationReport,
)
from app.modules.governance.moderation import types as Types


@dataclass
class AssessmentRow:
    entity: ModerationAssessment
    reports: list[ModerationAssessmentReport]


@dataclass
class PageRow:
    items: list
    next_cursor: Types.Cursor | None


async def get_report(session, report_id: UUID, *, lock=False, reporter_id=None):
    """선택적 신고자 범위와 행 잠금으로 신고를 조회한다."""
    stmt = select(ModerationReport).where(ModerationReport.id == report_id)
    if reporter_id is not None:
        stmt = stmt.where(ModerationReport.reporter_user_id == reporter_id)
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt.execution_options(populate_existing=True))


async def get_report_by_key(session, key):
    """재전송 키에 저장된 최초 신고를 조회한다."""
    return await session.scalar(
        select(ModerationReport).where(ModerationReport.request_key == key)
    )


async def create_report(session, values):
    """검증이 끝난 신고 값을 저장하고 DB 기본값을 반환한다."""
    entity = ModerationReport(**values)
    session.add(entity)
    await session.flush()
    return entity


async def update_report_intake(session, report_id, *, status, duplicate_id, reason):
    """호출자가 결정한 접수 상태와 중복 연결을 반영한다."""
    return await session.scalar(
        update(ModerationReport)
        .where(ModerationReport.id == report_id)
        .values(
            intake_status=status,
            duplicate_of_report_id=duplicate_id,
            intake_reason=reason,
        )
        .returning(ModerationReport)
        .execution_options(populate_existing=True)
    )


async def list_reports(session, command, *, reporter_id=None):
    """인가 범위·필터를 유지하며 시각과 ID 내림차순으로 신고를 조회한다."""
    model = ModerationReport
    stmt = select(model)
    if reporter_id is not None:
        stmt = stmt.where(model.reporter_user_id == reporter_id)
    if command.target_type is not None:
        stmt = stmt.where(
            model.target_type == command.target_type,
            model.target_id == command.target_id,
        )
    if command.intake_status is not None:
        stmt = stmt.where(model.intake_status == command.intake_status)
    if command.unassessed_only:
        stmt = stmt.where(
            ~select(ModerationAssessmentReport.report_id)
            .where(ModerationAssessmentReport.report_id == model.id)
            .exists()
        )
    if not command.include_legacy_reviewed:
        legacy_status = model.evidence_snapshot["legacy_moderation_flag"][
            "status"
        ].astext
        stmt = stmt.where(legacy_status.is_(None) | (legacy_status == "pending"))
    return await _fetch_review_page(
        session,
        stmt,
        created_at=model.received_at,
        id_column=model.id,
        cursor=command.cursor,
        limit=command.limit,
        max_limit=100,
        cursor_factory=Types.Cursor,
        page_factory=PageRow,
    )


async def get_assessment(session, assessment_id, *, lock=False):
    """평가와 명시적으로 조회한 근거 신고 연결을 raw 묶음으로 반환한다."""
    stmt = select(ModerationAssessment).where(ModerationAssessment.id == assessment_id)
    if lock:
        stmt = stmt.with_for_update()
    entity = await session.scalar(stmt.execution_options(populate_existing=True))
    if entity is None:
        return None
    links = list(
        (
            await session.scalars(
                select(ModerationAssessmentReport).where(
                    ModerationAssessmentReport.assessment_id == assessment_id
                )
            )
        ).all()
    )
    return AssessmentRow(entity, links)


async def get_assessment_by_key(session, key):
    """멱등 키의 평가 ID를 찾아 근거 연결과 함께 반환한다."""
    assessment_id = await session.scalar(
        select(ModerationAssessment.id).where(
            ModerationAssessment.evaluation_key == key
        )
    )
    return (
        None if assessment_id is None else await get_assessment(session, assessment_id)
    )


async def get_superseding_assessment(session, assessment_id):
    """이전 평가를 대체한 평가가 있는지 ID만 조회한다."""
    return await session.scalar(
        select(ModerationAssessment.id)
        .where(ModerationAssessment.supersedes_assessment_id == assessment_id)
        .limit(1)
    )


async def get_report_assessment_id(session, report_id):
    """이미 평가 근거로 사용된 신고의 평가 ID를 조회한다."""
    return await session.scalar(
        select(ModerationAssessmentReport.assessment_id)
        .where(ModerationAssessmentReport.report_id == report_id)
        .limit(1)
    )


async def get_active_reversal_id(session, action_id):
    """취소되지 않은 해제 요청을 찾아 중복 해제 생성을 막는 근거를 반환한다."""
    return await session.scalar(
        select(ModerationAction.id)
        .where(
            ModerationAction.reverses_action_id == action_id,
            ModerationAction.status != "cancelled",
        )
        .limit(1)
    )


async def create_assessment(session, values, reports):
    """평가와 여러 근거 신고를 같은 미종료 트랜잭션에 저장한다."""
    entity = ModerationAssessment(**values)
    session.add(entity)
    await session.flush()
    links = [
        ModerationAssessmentReport(
            assessment_id=entity.id,
            report_id=item.report_id,
            disposition=item.disposition,
        )
        for item in reports
    ]
    session.add_all(links)
    await session.flush()
    return AssessmentRow(entity, links)


async def list_assessments(session, command):
    """대상별 평가를 페이지 조회하고 해당 페이지의 근거를 한 번에 조회한다."""
    model = ModerationAssessment
    page = await _fetch_review_page(
        session,
        select(model).where(
            model.target_type == command.target_type,
            model.target_id == command.target_id,
        ),
        created_at=model.evaluated_at,
        id_column=model.id,
        cursor=command.cursor,
        limit=command.limit,
        max_limit=100,
        cursor_factory=Types.Cursor,
        page_factory=PageRow,
    )
    ids = [item.id for item in page.items]
    links = (
        list(
            (
                await session.scalars(
                    select(ModerationAssessmentReport).where(
                        ModerationAssessmentReport.assessment_id.in_(ids)
                    )
                )
            ).all()
        )
        if ids
        else []
    )
    return PageRow(
        [
            AssessmentRow(
                item, [link for link in links if link.assessment_id == item.id]
            )
            for item in page.items
        ],
        page.next_cursor,
    )


async def get_action(session, action_id, *, lock=False):
    """조치 단건을 조회하고 상태 변경 시 행을 잠근다."""
    stmt = select(ModerationAction).where(ModerationAction.id == action_id)
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt.execution_options(populate_existing=True))


async def get_action_by_key(session, key):
    """조치 멱등 키의 최초 요청을 조회한다."""
    return await session.scalar(
        select(ModerationAction).where(ModerationAction.idempotency_key == key)
    )


async def create_action(session, values):
    """pending 조치 요청을 저장하고 실제 대상 상태는 변경하지 않는다."""
    entity = ModerationAction(**values)
    session.add(entity)
    await session.flush()
    return entity


async def cancel_action(session, action_id):
    """호출자가 허용한 조치의 상태를 cancelled로 저장한다."""
    return await session.scalar(
        update(ModerationAction)
        .where(ModerationAction.id == action_id)
        .values(status="cancelled")
        .returning(ModerationAction)
        .execution_options(populate_existing=True)
    )


async def create_admin_audit(session, actor_id, action, target_id, metadata) -> None:
    """기존 감사 로그에 수동 관리자 변경의 행위자와 대상만 기록한다."""
    session.add(
        AuditLog(
            admin_id=actor_id, action=action, target_id=target_id, metadata_=metadata
        )
    )
    await session.flush()


async def list_actions(session, command):
    """평가·대상·상태 필터를 적용하고 조치 요청을 커서 조회한다."""
    model = ModerationAction
    stmt = select(model)
    if command.assessment_id is not None:
        stmt = stmt.where(model.assessment_id == command.assessment_id)
    if command.target_type is not None:
        stmt = stmt.where(
            model.target_type == command.target_type,
            model.target_id == command.target_id,
        )
    if command.statuses:
        stmt = stmt.where(model.status.in_(command.statuses))
    return await _fetch_review_page(
        session,
        stmt,
        created_at=model.created_at,
        id_column=model.id,
        cursor=command.cursor,
        limit=command.limit,
        max_limit=100,
        cursor_factory=Types.Cursor,
        page_factory=PageRow,
    )


async def _fetch_review_page(
    session,
    stmt,
    *,
    created_at,
    id_column,
    cursor,
    limit,
    max_limit,
    cursor_factory,
    page_factory,
):
    """received/evaluated/created 시각 컬럼에 맞춰 안정적인 페이지와 다음 커서를 만든다."""
    if cursor is not None:
        stmt = stmt.where(
            or_(
                created_at < cursor.created_at,
                and_(created_at == cursor.created_at, id_column < cursor.id),
            )
        )
    rows = list(
        (
            await session.scalars(
                stmt.order_by(created_at.desc(), id_column.desc()).limit(limit + 1)
            )
        ).all()
    )
    items = rows[:limit]
    next_cursor = (
        cursor_factory(getattr(items[-1], created_at.key), items[-1].id)
        if len(rows) > limit and items
        else None
    )
    return page_factory(items, next_cursor)
