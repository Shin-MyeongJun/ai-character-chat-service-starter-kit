"""실제 PostgreSQL에서 업무 저장·커서·동시 요청과 접근 경계를 검증한다."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.db.models.identity import User
from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.service.command import (
    actions as ActionsCommandService,
)
from app.modules.governance.moderation.service.command import (
    assessments as AssessmentsCommandService,
)
from app.modules.governance.moderation.service.command import (
    reports as ReportsCommandService,
)
from app.modules.governance.moderation.service.query import (
    actions as ActionsQueryService,
)
from app.modules.governance.moderation.service.query import (
    assessments as AssessmentsQueryService,
)
from app.modules.governance.moderation.service.query import (
    reports as ReportsQueryService,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_users(db):
    """새 테스트 스키마에만 신고자·관리자·대상 사용자를 준비한다."""
    ids = [uuid4() for _ in range(3)]
    db.add_all(
        [
            User(
                id=uid,
                email=f"{uid}@example.test",
                role="admin" if index == 1 else "user",
            )
            for index, uid in enumerate(ids)
        ]
    )
    await db.commit()
    return tuple(Types.ActorCommand(uid) for uid in ids)


def report_command(target_id):
    """사용자 대상 신고 입력을 생성한다."""
    return Types.SubmitReportCommand(
        request_key=uuid4(),
        target_type="user",
        target_id=target_id,
        reason_code="abuse",
    )


def assessment_command(report):
    """접수된 신고의 수동 평가 입력을 생성한다."""
    return Types.RecordAssessmentCommand(
        evaluation_key=str(uuid4()),
        target_type=report.target_type,
        target_id=report.target_id,
        policy_version="test-v1",
        outcome="violation",
        violation_code="abuse",
        rationale="테스트 증거 검토",
        reports=(Types.ReportDisposition(report.id, "supported"),),
    )


@pytest.mark.asyncio
async def test_real_report_assessment_action_and_pagination(db):
    """실제 저장·다대다 연결·대기 조치·취소와 동률 커서를 확인한다."""
    user, admin, target = await seed_users(db)
    reports = [
        await ReportsCommandService.submit_report(
            db, report_command(target.user_id), actor=user
        )
        for _ in range(3)
    ]
    # 동률 시각에도 ID 보조 정렬로 빠짐없이 페이지를 이어야 한다.
    await db.execute(
        text("UPDATE moderation_reports SET received_at=:time"),
        {"time": datetime.now(UTC)},
    )
    await db.commit()
    ids, cursor = [], None
    while True:
        page = await ReportsQueryService.list_own_reports(
            db, Types.ListReportsCommand(limit=1, cursor=cursor), actor=user
        )
        ids.extend(item.id for item in page.items)
        cursor = page.next_cursor
        await db.rollback()
        if cursor is None:
            break
    assert len(ids) == len(set(ids)) == 3
    with pytest.raises(Types.ModerationError, match="not_found"):
        await ReportsQueryService.get_own_report(
            db, Types.GetReportCommand(reports[0].id), actor=target
        )
    await db.rollback()
    command = replace(
        assessment_command(reports[0]),
        reports=tuple(
            Types.ReportDisposition(report.id, "supported") for report in reports
        ),
    )
    assessment = await AssessmentsCommandService.record_manual_assessment(
        db, command, actor=admin
    )
    assert len(assessment.reports) == 3
    queue = await ReportsQueryService.list_admin_reports(
        db,
        Types.ListReportsCommand(intake_status="received", unassessed_only=True),
        actor=admin,
    )
    assert not queue.items
    await db.rollback()
    with pytest.raises(Types.ModerationError, match="state_conflict"):
        await ReportsCommandService.change_report_intake(
            db,
            Types.ChangeReportIntakeCommand(
                report_id=reports[0].id,
                intake_status="rejected",
                reason="평가 이후 거절",
            ),
            actor=admin,
        )
    with pytest.raises(Types.ModerationError, match="not_found"):
        await AssessmentsCommandService.record_manual_assessment(
            db,
            replace(
                command,
                evaluation_key=str(uuid4()),
                reports=(Types.ReportDisposition(uuid4(), "supported"),),
            ),
            actor=admin,
        )
    assert await db.scalar(text("SELECT count(*) FROM moderation_assessments")) == 1
    await db.rollback()
    evaluation_page = await AssessmentsQueryService.list_assessments(
        db,
        Types.ListAssessmentsCommand(target_type="user", target_id=target.user_id),
        actor=admin,
    )
    assert evaluation_page.items[0].id == assessment.id
    await db.rollback()
    action_command = Types.RequestActionCommand(
        assessment_id=assessment.id,
        target_type="user",
        target_id=target.user_id,
        action_type="restrict",
        scope="publish",
        starts_at=datetime.now(UTC),
        idempotency_key=uuid4(),
    )
    first = await ActionsCommandService.request_action(db, action_command, actor=admin)
    second = await ActionsCommandService.request_action(
        db, replace(action_command, scope="login", idempotency_key=uuid4()), actor=admin
    )
    retry = await ActionsQueryService.list_retry_actions(
        db, Types.ListActionsCommand(limit=1), actor=admin
    )
    assert retry.next_cursor is not None and len(retry.items) == 1
    await db.rollback()
    cancelled = await ActionsCommandService.cancel_pending_action(
        db, Types.CancelActionCommand(first.id), actor=admin
    )
    assert cancelled.status == "cancelled" and second.status == "pending"
    assert (
        await db.scalar(
            text("SELECT status FROM users WHERE id=:id"), {"id": target.user_id}
        )
        == "active"
    )
    await db.rollback()


@pytest.mark.asyncio
async def test_real_concurrent_report_and_reassessment(db):
    """독립 세션의 동시 접수는 한 건이며 동일 이전 평가의 재평가는 한 건만 성공한다."""
    user, admin, target = await seed_users(db)
    command = report_command(target.user_id)

    async def submit():
        """각 요청을 실제 독립 트랜잭션으로 실행한다."""
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await ReportsCommandService.submit_report(
                session, command, actor=user
            )

    a, b = await asyncio.wait_for(asyncio.gather(submit(), submit()), timeout=15)
    assert a.id == b.id
    previous = await AssessmentsCommandService.record_manual_assessment(
        db, assessment_command(a), actor=admin
    )

    async def reassess():
        """다른 키로 같은 이전 평가를 동시에 대체한다."""
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await AssessmentsCommandService.record_manual_assessment(
                session,
                replace(assessment_command(a), supersedes_assessment_id=previous.id),
                actor=admin,
            )

    results = await asyncio.wait_for(
        asyncio.gather(reassess(), reassess(), return_exceptions=True), timeout=15
    )
    assert sum(isinstance(result, Types.AssessmentInfo) for result in results) == 1
    assert (
        sum(
            isinstance(result, Types.ModerationError)
            and result.code == "state_conflict"
            for result in results
        )
        == 1
    )


@pytest.mark.asyncio
async def test_real_product_access_snapshot_and_changed_original_retry(db):
    """비공개 접근·타 작품 버전을 거절하고 최초 접수 증거를 재호출에도 유지한다."""
    user, admin, owner = await seed_users(db)
    product_id, other_id, snapshot_id, other_snapshot = [uuid4() for _ in range(4)]
    db.add_all(
        [
            Product(
                id=product_id,
                owner_id=owner.user_id,
                title="원본",
                visibility="private",
                status="approved",
            ),
            Product(id=other_id, owner_id=owner.user_id, title="다른 작품"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            ProductSnapshot(
                id=snapshot_id,
                product_id=product_id,
                version=1,
                snapshot_data={"title": "발행 제목", "description": "증거"},
            ),
            ProductSnapshot(
                id=other_snapshot,
                product_id=other_id,
                version=1,
                snapshot_data={"title": "다른 제목"},
            ),
        ]
    )
    await db.flush()
    await db.execute(
        text("UPDATE products SET latest_snapshot_id=:sid WHERE id=:pid"),
        {"sid": snapshot_id, "pid": product_id},
    )
    await db.commit()
    command = Types.SubmitReportCommand(
        request_key=uuid4(),
        target_type="product",
        target_id=product_id,
        target_snapshot_id=snapshot_id,
        reason_code="abuse",
    )
    with pytest.raises(Types.ModerationError, match="target_unavailable"):
        await ReportsCommandService.submit_report(db, command, actor=user)
    await db.execute(
        text("UPDATE products SET visibility='public' WHERE id=:id"), {"id": product_id}
    )
    await db.commit()
    with pytest.raises(Types.ModerationError, match="target_unavailable"):
        await ReportsCommandService.submit_report(
            db, replace(command, target_snapshot_id=other_snapshot), actor=user
        )
    report = await ReportsCommandService.submit_report(db, command, actor=user)
    detail = await ReportsQueryService.get_admin_report(
        db, Types.GetReportCommand(report.id), actor=admin
    )
    assert (
        detail.target_owner_user_id == owner.user_id
        and detail.evidence_snapshot["server"]["title"] == "발행 제목"
    )
    await db.rollback()
    await db.execute(
        text("UPDATE products SET visibility='private' WHERE id=:id"),
        {"id": product_id},
    )
    await db.commit()
    assert await ReportsCommandService.submit_report(db, command, actor=user) == report
    with pytest.raises(Types.ModerationError, match="target_unavailable"):
        await ReportsCommandService.submit_report(
            db, replace(command, request_key=uuid4()), actor=user
        )


@pytest.mark.asyncio
async def test_real_legacy_completed_reports_excluded_from_default_queue(db):
    """과거 검토 완료 건은 기본 대기 목록에서 제외하고 명시 옵션으로 조회한다."""
    user, admin, target = await seed_users(db)
    report = await ReportsCommandService.submit_report(
        db, report_command(target.user_id), actor=user
    )
    await db.execute(
        text(
            "UPDATE moderation_reports SET evidence_snapshot=jsonb_build_object('legacy_moderation_flag',jsonb_build_object('status','reviewed')) WHERE id=:id"
        ),
        {"id": report.id},
    )
    await db.commit()
    page = await ReportsQueryService.list_admin_reports(
        db, Types.ListReportsCommand(), actor=admin
    )
    assert not page.items
    await db.rollback()
    page = await ReportsQueryService.list_admin_reports(
        db, Types.ListReportsCommand(include_legacy_reviewed=True), actor=admin
    )
    assert page.items[0].id == report.id
