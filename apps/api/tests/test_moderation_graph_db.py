"""실제 PostgreSQL에서 대상별 신고 그래프 잠금과 평가 일괄 조회를 검증한다."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import TypeVar
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_moderation_services_db import assessment_command, report_command, seed_users

from app.db.models.moderation_review import ModerationReport
from app.db.transaction import use_case_transaction
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
from app.modules.governance.moderation.service.command import (
    assessments as AssessmentsCommandService,
)
from app.modules.governance.moderation.service.command import (
    reports as ReportsCommandService,
)

T = TypeVar("T")
Operation = Callable[[AsyncSession], Awaitable[Types.ReportInfo | Types.AssessmentInfo]]


@asynccontextmanager
async def running_operation(
    db: AsyncSession,
    operation: Callable[[AsyncSession], Awaitable[T]],
    *,
    written: asyncio.Event | None = None,
    release: asyncio.Event | None = None,
) -> AsyncIterator[tuple[asyncio.Task[T], int]]:
    """각 요청을 독립 세션으로 실행하고 필요하면 외곽 commit 직전에 멈춘다."""
    pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def run() -> T:
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            async with use_case_transaction(session):
                backend_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                pid.set_result(backend_pid)
                result = await operation(session)
                if written is not None:
                    written.set()
                if release is not None:
                    await release.wait()
                return result

    task = asyncio.create_task(run())
    try:
        yield task, await asyncio.wait_for(pid, timeout=10)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def wait_for_advisory_wait(db: AsyncSession, waiter: int, holder: int) -> None:
    """시간 추측 대신 PostgreSQL의 실제 advisory 대기와 차단 PID를 확인한다."""

    async def observe() -> None:
        async with AsyncSession(db.bind) as session:
            while True:
                blocked = await session.scalar(
                    text(
                        "SELECT wait_event = 'advisory' "
                        "AND :holder = ANY(pg_blocking_pids(pid)) "
                        "FROM pg_stat_activity WHERE pid = :waiter"
                    ),
                    {"holder": holder, "waiter": waiter},
                )
                # pg_stat_activity의 트랜잭션별 통계 스냅샷을 재사용하지 않는다.
                await session.rollback()
                if blocked:
                    return
                await asyncio.sleep(0.01)

    await asyncio.wait_for(observe(), timeout=5)


def operation_for(
    kind: str, report: Types.ReportSummaryInfo, admin: Types.ActorCommand
) -> Operation:
    """접수 거절 또는 평가를 동일한 실행 형태로 준비한다."""

    async def execute(session: AsyncSession) -> Types.ReportInfo | Types.AssessmentInfo:
        if kind == "intake":
            return await ReportsCommandService.change_report_intake(
                session,
                Types.ChangeReportIntakeCommand(
                    report_id=report.id, intake_status="rejected", reason="검토 종료"
                ),
                actor=admin,
            )
        return await AssessmentsCommandService.record_manual_assessment(
            session, assessment_command(report), actor=admin
        )

    return execute


@pytest.mark.asyncio
@pytest.mark.parametrize("first_kind", ["intake", "assessment"])
@pytest.mark.parametrize("second_kind", ["intake", "assessment"])
@pytest.mark.parametrize("scope", ["same_target", "different_id", "different_type"])
async def test_target_lock_scope(db, first_kind, second_kind, scope):
    """동일 대상의 서로 다른 신고만 대기하고 다른 ID/종류는 commit 전에 완료한다."""
    user, admin, target = await seed_users(db)
    first = await ReportsCommandService.submit_report(
        db, report_command(target.user_id), actor=user
    )
    if scope == "different_type":
        # 기존 character 신고도 평가 가능하며 user와 UUID가 같아도 독립 대상이다.
        entity = ModerationReport(
            request_key=uuid4(),
            reporter_user_id=user.user_id,
            target_type="character",
            target_id=target.user_id,
            reason_code="abuse",
        )
        db.add(entity)
        await db.commit()
        second = PersistenceMapper.report_info_to_summary(
            PersistenceMapper.report_entity_to_info(entity)
        )
    else:
        second = await ReportsCommandService.submit_report(
            db,
            report_command(user.user_id if scope == "different_id" else target.user_id),
            actor=user,
        )
    written, release = asyncio.Event(), asyncio.Event()
    async with running_operation(
        db, operation_for(first_kind, first, admin), written=written, release=release
    ) as (holder_task, holder_pid):
        await asyncio.wait_for(written.wait(), timeout=5)
        async with running_operation(db, operation_for(second_kind, second, admin)) as (
            waiter_task,
            waiter_pid,
        ):
            if scope == "same_target":
                await wait_for_advisory_wait(db, waiter_pid, holder_pid)
                release.set()
            await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
            release.set()
            await asyncio.wait_for(asyncio.shield(holder_task), timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("chain_length", [2, 3])
async def test_concurrent_duplicate_links_cannot_close_cycle(db, chain_length):
    """반대 방향 연결과 세 노드 간접 순환을 commit 후 최신 체인으로 거절한다."""
    user, admin, target = await seed_users(db)
    reports = [
        await ReportsCommandService.submit_report(
            db, report_command(target.user_id), actor=user
        )
        for _ in range(chain_length)
    ]

    async def link(session: AsyncSession, source: int, parent: int) -> Types.ReportInfo:
        return await ReportsCommandService.change_report_intake(
            session,
            Types.ChangeReportIntakeCommand(
                report_id=reports[source].id,
                intake_status="duplicate",
                duplicate_of_report_id=reports[parent].id,
                reason="중복 연결",
            ),
            actor=admin,
        )

    if chain_length == 3:
        await link(db, 1, 2)
    written, release = asyncio.Event(), asyncio.Event()
    async with running_operation(
        db, lambda session: link(session, 0, 1), written=written, release=release
    ) as (holder_task, holder_pid):
        await asyncio.wait_for(written.wait(), timeout=5)
        async with running_operation(
            db, lambda session: link(session, chain_length - 1, 0)
        ) as (waiter_task, waiter_pid):
            await wait_for_advisory_wait(db, waiter_pid, holder_pid)
            release.set()
            await asyncio.wait_for(asyncio.shield(holder_task), timeout=5)
            with pytest.raises(Types.ModerationError, match="invalid_link"):
                await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
    assert (
        await db.scalar(
            text(
                "SELECT count(*) FROM moderation_reports WHERE intake_status='duplicate'"
            )
        )
        == chain_length - 1
    )
    assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == chain_length - 1


@pytest.mark.asyncio
@pytest.mark.parametrize("same_reason", [False, True])
async def test_intake_waiter_rechecks_terminal_state(db, same_reason):
    """대기 전 received였어도 최신 종결 상태로 멱등 재사용 또는 충돌을 판단한다."""
    user, admin, target = await seed_users(db)
    report = await ReportsCommandService.submit_report(
        db, report_command(target.user_id), actor=user
    )
    written, release = asyncio.Event(), asyncio.Event()

    async def second_intake(session: AsyncSession) -> Types.ReportInfo:
        return await ReportsCommandService.change_report_intake(
            session,
            Types.ChangeReportIntakeCommand(
                report_id=report.id,
                intake_status="rejected",
                reason="검토 종료" if same_reason else "다른 사유",
            ),
            actor=admin,
        )

    async with running_operation(
        db, operation_for("intake", report, admin), written=written, release=release
    ) as (holder_task, holder_pid):
        await asyncio.wait_for(written.wait(), timeout=5)
        async with running_operation(db, second_intake) as (waiter_task, waiter_pid):
            await wait_for_advisory_wait(db, waiter_pid, holder_pid)
            release.set()
            first = await asyncio.wait_for(asyncio.shield(holder_task), timeout=5)
            if same_reason:
                assert (
                    await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
                    == first
                )
            else:
                with pytest.raises(Types.ModerationError, match="state_conflict"):
                    await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
    assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == 1


@pytest.mark.asyncio
async def test_overlapping_cross_target_batches_are_rejected_without_deadlock(db):
    """서로 다른 대상의 잘못된 교차 근거 목록도 같은 행 순서로 잠그고 거절한다."""
    user, admin, target = await seed_users(db)
    reports = [
        await ReportsCommandService.submit_report(
            db, report_command(target_id), actor=user
        )
        for target_id in (user.user_id, target.user_id)
    ]
    commands = [
        replace(
            assessment_command(report),
            reports=tuple(
                Types.ReportDisposition(item.id, "supported") for item in reports
            ),
        )
        for report in reports
    ]
    async with running_operation(
        db,
        lambda session: AssessmentsCommandService.record_manual_assessment(
            session, commands[0], actor=admin
        ),
    ) as (first, _):
        async with running_operation(
            db,
            lambda session: AssessmentsCommandService.record_manual_assessment(
                session, commands[1], actor=admin
            ),
        ) as (second, _):
            results = await asyncio.wait_for(
                asyncio.gather(first, second, return_exceptions=True), timeout=5
            )
    assert all(
        isinstance(result, Types.ModerationError) and result.code == "invalid_link"
        for result in results
    )
    assert await db.scalar(text("SELECT count(*) FROM moderation_assessments")) == 0
    assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("assessment_first", [False, True])
@pytest.mark.parametrize("intake_status", ["rejected", "duplicate"])
async def test_intake_and_assessment_conflict_in_both_orders(
    db, assessment_first, intake_status
):
    """동일 신고의 평가와 접수 종결 중 먼저 commit한 상태만 유효하다."""
    user, admin, target = await seed_users(db)
    report, parent = [
        await ReportsCommandService.submit_report(
            db, report_command(target.user_id), actor=user
        )
        for _ in range(2)
    ]

    async def intake(session: AsyncSession) -> Types.ReportInfo:
        return await ReportsCommandService.change_report_intake(
            session,
            Types.ChangeReportIntakeCommand(
                report_id=report.id,
                intake_status=intake_status,
                reason="접수 종료",
                duplicate_of_report_id=parent.id
                if intake_status == "duplicate"
                else None,
            ),
            actor=admin,
        )

    assess = operation_for("assessment", report, admin)
    first, second = (assess, intake) if assessment_first else (intake, assess)
    written, release = asyncio.Event(), asyncio.Event()
    async with running_operation(db, first, written=written, release=release) as (
        holder_task,
        holder_pid,
    ):
        await asyncio.wait_for(written.wait(), timeout=5)
        async with running_operation(db, second) as (waiter_task, waiter_pid):
            await wait_for_advisory_wait(db, waiter_pid, holder_pid)
            release.set()
            await asyncio.wait_for(asyncio.shield(holder_task), timeout=5)
            code = "state_conflict" if assessment_first else "invalid_link"
            with pytest.raises(Types.ModerationError, match=code):
                await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
    assert await db.scalar(text("SELECT count(*) FROM moderation_assessments")) == int(
        assessment_first
    )
    assert await db.scalar(
        text("SELECT count(*) FROM moderation_assessment_reports")
    ) == int(assessment_first)
    assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_holder", [False, True])
async def test_rollback_or_cancel_releases_target_and_restores_report(
    db, cancel_holder
):
    """외곽 실패·취소 시 접수/감사가 롤백되고 대기 평가는 received를 읽는다."""
    user, admin, target = await seed_users(db)
    report = await ReportsCommandService.submit_report(
        db, report_command(target.user_id), actor=user
    )
    written, release = asyncio.Event(), asyncio.Event()

    async def fail_intake(session: AsyncSession) -> None:
        await operation_for("intake", report, admin)(session)
        written.set()
        await release.wait()
        raise RuntimeError("outer failure")

    async with running_operation(db, fail_intake) as (holder_task, holder_pid):
        await asyncio.wait_for(written.wait(), timeout=5)
        async with running_operation(
            db, operation_for("assessment", report, admin)
        ) as (waiter_task, waiter_pid):
            await wait_for_advisory_wait(db, waiter_pid, holder_pid)
            if cancel_holder:
                holder_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await holder_task
            else:
                release.set()
                with pytest.raises(RuntimeError, match="outer failure"):
                    await asyncio.wait_for(asyncio.shield(holder_task), timeout=5)
            await asyncio.wait_for(asyncio.shield(waiter_task), timeout=5)
    assert (
        await db.scalar(text("SELECT intake_status FROM moderation_reports"))
        == "received"
    )
    assert await db.scalar(text("SELECT count(*) FROM audit_logs")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("report_count", [1, 10, 100])
async def test_assessment_uses_one_fresh_report_query(db, report_count):
    """근거 1..100건은 한 SELECT로 읽고 신호·정규화·멱등 재사용을 유지한다."""
    user, admin, target = await seed_users(db)
    entities = [
        ModerationReport(
            id=uuid4(),
            request_key=uuid4(),
            reporter_user_id=user.user_id,
            target_type="user",
            target_id=target.user_id,
            reason_code="abuse",
        )
        for _ in range(report_count)
    ]
    db.add_all(entities)
    await db.commit()
    reports = [PersistenceMapper.report_entity_to_info(entity) for entity in entities]
    command = replace(
        assessment_command(reports[0]),
        reports=tuple(
            Types.ReportDisposition(report.id, "supported")
            for report in reversed(reports)
        ),
    )
    statements: list[str] = []

    def count_sql(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        assessment = await AssessmentsCommandService.record_manual_assessment(
            db, command, actor=admin
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    report_selects = [sql for sql in statements if "FROM moderation_reports" in sql]
    print(
        f"reports={report_count}: report_selects={len(report_selects)}, total_sql={len(statements)}"
    )
    assert len(report_selects) == 1
    assert "ORDER BY moderation_reports.id" in report_selects[0]
    assert "FOR UPDATE" in report_selects[0]
    assert assessment.signals["verified_report_count"] == report_count
    assert assessment.signals["verified_distinct_reporter_count"] == 1
    assert [link.report_id for link in assessment.reports] == sorted(
        report.id for report in reports
    )
    assert (
        await AssessmentsCommandService.record_manual_assessment(
            db,
            replace(command, reports=command.reports + command.reports[:1])
            if report_count < 100
            else command,
            actor=admin,
        )
        == assessment
    )


@pytest.mark.asyncio
async def test_batch_report_lookup_refreshes_loaded_entities(db):
    """같은 세션에 이미 적재한 신고도 일괄 잠금 조회에서 최신 상태로 갱신한다."""
    user, admin, target = await seed_users(db)
    report = await ReportsCommandService.submit_report(
        db, report_command(target.user_id), actor=user
    )
    async with AsyncSession(db.bind, expire_on_commit=False) as session:
        stale = await ReviewRepository.get_report(session, report.id)
        assert stale.intake_status == "received"
        await session.commit()
        await operation_for("intake", report, admin)(db)
        with pytest.raises(Types.ModerationError, match="invalid_link"):
            await AssessmentsCommandService.record_manual_assessment(
                session, assessment_command(report), actor=admin
            )
    assert await db.scalar(text("SELECT count(*) FROM moderation_assessments")) == 0


@pytest.mark.asyncio
async def test_foreign_assessment_does_not_lock_duplicate_parent(db, monkeypatch):
    """타 대상의 잘못된 평가가 중복 부모를 잠가 FK 갱신과 교착하지 않는다."""
    user, admin, target = await seed_users(db)
    parent, source = sorted(
        [
            await ReportsCommandService.submit_report(
                db, report_command(target.user_id), actor=user
            )
            for _ in range(2)
        ],
        key=lambda report: report.id,
    )
    ready, release = asyncio.Event(), asyncio.Event()
    update_intake = ReviewRepository.update_report_intake

    async def pause_before_fk_update(session, report_id, **kwargs):
        ready.set()
        await release.wait()
        return await update_intake(session, report_id, **kwargs)

    monkeypatch.setattr(
        ReviewRepository, "update_report_intake", pause_before_fk_update
    )

    async def link(session: AsyncSession) -> Types.ReportInfo:
        return await ReportsCommandService.change_report_intake(
            session,
            Types.ChangeReportIntakeCommand(
                report_id=source.id,
                intake_status="duplicate",
                duplicate_of_report_id=parent.id,
                reason="중복",
            ),
            actor=admin,
        )

    command = replace(
        assessment_command(source),
        target_id=user.user_id,
        reports=tuple(
            Types.ReportDisposition(report.id, "supported")
            for report in (parent, source)
        ),
    )
    async with running_operation(db, link) as (holder, _):
        await asyncio.wait_for(ready.wait(), timeout=5)
        async with running_operation(
            db,
            lambda session: AssessmentsCommandService.record_manual_assessment(
                session, command, actor=admin
            ),
        ) as (invalid, _):
            with pytest.raises(Types.ModerationError, match="invalid_link"):
                await asyncio.wait_for(asyncio.shield(invalid), timeout=5)
            release.set()
            result = await asyncio.wait_for(asyncio.shield(holder), timeout=5)
            assert result.duplicate_of_report_id == parent.id
    assert await db.scalar(text("SELECT count(*) FROM moderation_assessments")) == 0
