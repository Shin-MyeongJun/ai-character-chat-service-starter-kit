"""신고·평가·조치 저장과 잠금. 업무 판단과 트랜잭션 종료는 수행하지 않는다."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypedDict, TypeVar
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import Select

from app.db.models.moderation import AuditLog
from app.db.models.moderation_review import (
    ModerationAction,
    ModerationAssessment,
    ModerationAssessmentReport,
    ModerationReport,
)
from app.modules.governance.moderation import types as Types


class ReportCreateValues(TypedDict):
    """신고 서비스가 검증·확보한 최초 저장 값. 생략한 열은 DB 기본값이다."""

    request_key: UUID
    reporter_user_id: UUID
    target_type: str
    target_id: UUID
    target_owner_user_id: UUID | None
    target_snapshot_id: UUID | None
    reason_code: str
    reason_detail: str | None
    occurred_at: datetime | None
    received_at: datetime
    form_elapsed_ms: int | None
    evidence_snapshot: Types.JsonObject
    attachment_refs: list[Types.JsonValue]
    evidence_captured_at: datetime
    intake_status: str


class AssessmentCreateValues(TypedDict):
    """평가 이력의 추가 입력. 기존 평가를 수정하는 입력은 제공하지 않는다."""

    target_type: str
    target_id: UUID
    assessment_type: str
    evaluator_user_id: UUID
    policy_version: str
    evaluated_at: datetime
    window_start: datetime | None
    window_end: datetime | None
    signals: Types.JsonObject
    confidence_score: Decimal | None
    outcome: str
    violation_code: str | None
    severity: int | None
    recommended_actions: list[Types.JsonValue]
    rationale: str
    supersedes_assessment_id: UUID | None
    evaluation_key: str


class ActionCreateValues(TypedDict):
    """조치 요청 필드와 초기 상태. 실제 적용 결과는 DB 기본값으로 남긴다."""

    assessment_id: UUID
    target_type: str
    target_id: UUID
    action_type: str
    scope: str
    starts_at: datetime
    ends_at: datetime | None
    idempotency_key: UUID
    reverses_action_id: UUID | None
    status: str


T = TypeVar("T")


@dataclass
class AssessmentRow:
    entity: ModerationAssessment
    reports: list[ModerationAssessmentReport]


@dataclass
class PageRow(Generic[T]):
    items: list[T]
    next_cursor: Types.Cursor | None


async def get_report(
    session: AsyncSession,
    report_id: UUID,
    *,
    lock: bool = False,
    reporter_id: UUID | None = None,
) -> ModerationReport | None:
    """선택적 신고자 범위와 행 잠금으로 신고를 조회한다."""
    stmt = select(ModerationReport).where(ModerationReport.id == report_id)
    if reporter_id is not None:
        stmt = stmt.where(ModerationReport.reporter_user_id == reporter_id)
    if lock:
        stmt = stmt.with_for_update()
    return (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).first()


async def get_report_by_key(
    session: AsyncSession, key: UUID
) -> ModerationReport | None:
    """재전송 키에 저장된 최초 신고를 조회한다."""
    return (
        await session.scalars(
            select(ModerationReport).where(ModerationReport.request_key == key)
        )
    ).first()


async def create_report(
    session: AsyncSession, values: ReportCreateValues
) -> ModerationReport:
    """검증이 끝난 신고 값을 저장하고 DB 기본값을 반환한다."""
    entity = ModerationReport(**values)
    session.add(entity)
    await session.flush()
    return entity


async def update_report_intake(
    session: AsyncSession,
    report_id: UUID,
    *,
    status: str,
    duplicate_id: UUID | None,
    reason: str,
) -> ModerationReport | None:
    """호출자가 결정한 접수 상태와 중복 연결을 반영한다."""
    return (
        await session.scalars(
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
    ).first()


async def list_reports(
    session: AsyncSession,
    command: Types.ListReportsCommand,
    *,
    reporter_id: UUID | None = None,
) -> PageRow[ModerationReport]:
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
        cursor_from_entity=lambda item: Types.Cursor(item.received_at, item.id),
    )


async def get_assessment(
    session: AsyncSession, assessment_id: UUID, *, lock: bool = False
) -> AssessmentRow | None:
    """평가와 명시적으로 조회한 근거 신고 연결을 raw 묶음으로 반환한다."""
    stmt = select(ModerationAssessment).where(ModerationAssessment.id == assessment_id)
    if lock:
        stmt = stmt.with_for_update()
    entity = (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).first()
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


async def get_assessment_by_key(
    session: AsyncSession, key: str
) -> AssessmentRow | None:
    """멱등 키의 평가 ID를 찾아 근거 연결과 함께 반환한다."""
    assessment_id = (
        await session.scalars(
            select(ModerationAssessment.id).where(
                ModerationAssessment.evaluation_key == key
            )
        )
    ).first()
    return (
        None if assessment_id is None else await get_assessment(session, assessment_id)
    )


async def get_superseding_assessment(
    session: AsyncSession, assessment_id: UUID
) -> UUID | None:
    """이전 평가를 대체한 평가가 있는지 ID만 조회한다."""
    return (
        await session.scalars(
            select(ModerationAssessment.id)
            .where(ModerationAssessment.supersedes_assessment_id == assessment_id)
            .limit(1)
        )
    ).first()


async def get_report_assessment_id(
    session: AsyncSession, report_id: UUID
) -> UUID | None:
    """이미 평가 근거로 사용된 신고의 평가 ID를 조회한다."""
    return (
        await session.scalars(
            select(ModerationAssessmentReport.assessment_id)
            .where(ModerationAssessmentReport.report_id == report_id)
            .limit(1)
        )
    ).first()


async def get_active_reversal_id(session: AsyncSession, action_id: UUID) -> UUID | None:
    """취소되지 않은 해제 요청을 찾아 중복 해제 생성을 막는 근거를 반환한다."""
    return (
        await session.scalars(
            select(ModerationAction.id)
            .where(
                ModerationAction.reverses_action_id == action_id,
                ModerationAction.status != "cancelled",
            )
            .limit(1)
        )
    ).first()


async def create_assessment(
    session: AsyncSession,
    values: AssessmentCreateValues,
    reports: Sequence[Types.ReportDisposition],
) -> AssessmentRow:
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


async def list_assessments(
    session: AsyncSession, command: Types.ListAssessmentsCommand
) -> PageRow[AssessmentRow]:
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
        cursor_from_entity=lambda item: Types.Cursor(item.evaluated_at, item.id),
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


async def get_action(
    session: AsyncSession, action_id: UUID, *, lock: bool = False
) -> ModerationAction | None:
    """조치 단건을 조회하고 상태 변경 시 행을 잠근다."""
    stmt = select(ModerationAction).where(ModerationAction.id == action_id)
    if lock:
        stmt = stmt.with_for_update()
    return (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).first()


async def get_action_by_key(
    session: AsyncSession, key: UUID
) -> ModerationAction | None:
    """조치 멱등 키의 최초 요청을 조회한다."""
    return (
        await session.scalars(
            select(ModerationAction).where(ModerationAction.idempotency_key == key)
        )
    ).first()


async def create_action(
    session: AsyncSession, values: ActionCreateValues
) -> ModerationAction:
    """pending 조치 요청을 저장하고 실제 대상 상태는 변경하지 않는다."""
    entity = ModerationAction(**values)
    session.add(entity)
    await session.flush()
    return entity


async def cancel_action(
    session: AsyncSession, action_id: UUID
) -> ModerationAction | None:
    """호출자가 허용한 조치의 상태를 cancelled로 저장한다."""
    return (
        await session.scalars(
            update(ModerationAction)
            .where(ModerationAction.id == action_id)
            .values(status="cancelled")
            .returning(ModerationAction)
            .execution_options(populate_existing=True)
        )
    ).first()


async def create_admin_audit(
    session: AsyncSession,
    actor_id: UUID,
    action: str,
    target_id: UUID | None,
    metadata: Types.JsonObject,
) -> None:
    """기존 감사 로그에 수동 관리자 변경의 행위자와 대상만 기록한다."""
    session.add(
        AuditLog(
            admin_id=actor_id, action=action, target_id=target_id, metadata_=metadata
        )
    )
    await session.flush()


async def list_actions(
    session: AsyncSession, command: Types.ListActionsCommand
) -> PageRow[ModerationAction]:
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
        cursor_from_entity=lambda item: Types.Cursor(item.created_at, item.id),
    )


async def _fetch_review_page(
    session: AsyncSession,
    stmt: Select[tuple[T]],
    *,
    created_at: InstrumentedAttribute[datetime],
    id_column: InstrumentedAttribute[UUID],
    cursor: Types.Cursor | None,
    limit: int,
    cursor_from_entity: Callable[[T], Types.Cursor],
) -> PageRow[T]:
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
    next_cursor = cursor_from_entity(items[-1]) if len(rows) > limit and items else None
    return PageRow(items, next_cursor)
