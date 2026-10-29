"""업무 경계는 대역으로, 저장·동시성·페이지는 별도 PostgreSQL 검사로 검증한다."""

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.modules.governance.moderation import types as Types
from app.modules.governance.moderation.mapper import persistence as PersistenceMapper
from app.modules.governance.moderation.repository import review as ReviewRepository
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
    reports as ReportsQueryService,
)
from app.modules.governance.moderation.service.util import (
    validation as ValidationServiceUtil,
)


@pytest.fixture
def memory_backend(monkeypatch):
    """DB 검증과 구분된 저장소 대역으로 서비스 분기·롤백 계약을 검사한다."""
    store = {"reports": {}, "assessments": {}, "actions": {}}
    user, admin, other = [Types.ActorCommand(uuid4()) for _ in range(3)]

    class Session:
        def __init__(self):
            """대역 세션마다 트랜잭션 참여 상태를 분리한다."""
            self.info = {}

        @asynccontextmanager
        async def begin(self):
            """업무 실패 시 대역 데이터도 이전 상태로 복원한다."""
            before = deepcopy(store)
            try:
                yield
            except BaseException:
                store.clear()
                store.update(before)
                raise

    async def active(session, command):
        """활성 사용자만 인증 상태 확인 대역에서 허용한다."""
        if command.user_id not in {user.user_id, admin.user_id, other.user_id}:
            raise LookupError()

    async def administrative(session, command):
        """관리자 ID만 역할 확인 대역에서 허용한다."""
        if command.user_id != admin.user_id:
            raise LookupError()

    async def target_user(session, command):
        """사용자 대상 존재 확인 대역을 반환한다."""
        return command.user_id

    async def lock(session, namespace, key):
        """순차 대역 검사에서는 SQL 잠금을 생략한다. 동시성 검증은 DB 테스트가 담당한다."""

    async def audit(session, actor_id, action, target_id, metadata):
        """기존 감사 스키마 기록 대역을 유지한다."""

    async def create_report(session, values):
        """DB 기본값에 대응하는 대역 신고를 만든다."""
        row = SimpleNamespace(
            id=uuid4(),
            duplicate_of_report_id=None,
            intake_reason=None,
            **deepcopy(values),
        )
        store["reports"][row.id] = row
        return row

    async def get_report(session, report_id, *, lock=False, reporter_id=None):
        """대역에서도 본인 조회 범위를 적용한다."""
        row = store["reports"].get(report_id)
        return (
            row
            if row is not None
            and (reporter_id is None or reporter_id == row.reporter_user_id)
            else None
        )

    async def report_key(session, key):
        """대역 신고의 멱등 키를 찾는다."""
        return next(
            (row for row in store["reports"].values() if row.request_key == key), None
        )

    async def change_intake(session, report_id, *, status, duplicate_id, reason):
        """대역의 접수 상태를 저장한다."""
        row = store["reports"][report_id]
        row.intake_status, row.duplicate_of_report_id, row.intake_reason = (
            status,
            duplicate_id,
            reason,
        )
        return row

    async def create_assessment(session, values, reports):
        """평가와 근거 묶음을 대역에 저장한다."""
        row = ReviewRepository.AssessmentRow(
            SimpleNamespace(id=uuid4(), **deepcopy(values)),
            [
                SimpleNamespace(report_id=item.report_id, disposition=item.disposition)
                for item in reports
            ],
        )
        store["assessments"][row.entity.id] = row
        return row

    async def get_assessment(session, key, *, lock=False):
        """대역 평가를 ID로 조회한다."""
        return store["assessments"].get(key)

    async def assessment_key(session, key):
        """대역 평가를 멱등 키로 조회한다."""
        return next(
            (
                row
                for row in store["assessments"].values()
                if row.entity.evaluation_key == key
            ),
            None,
        )

    async def successor(session, key):
        """이전 평가의 후속 판단을 찾는다."""
        return next(
            (
                row.entity.id
                for row in store["assessments"].values()
                if row.entity.supersedes_assessment_id == key
            ),
            None,
        )

    async def report_assessment(session, key):
        """신고를 사용한 기존 평가 대역을 찾는다."""
        return next(
            (
                row.entity.id
                for row in store["assessments"].values()
                if any(link.report_id == key for link in row.reports)
            ),
            None,
        )

    async def active_reversal(session, key):
        """취소되지 않은 해제 요청 대역을 찾는다."""
        return next(
            (
                row.id
                for row in store["actions"].values()
                if row.reverses_action_id == key and row.status != "cancelled"
            ),
            None,
        )

    async def create_action(session, values):
        """실제 제재 없이 조치 대역 행만 저장한다."""
        row = SimpleNamespace(
            id=uuid4(),
            domain_action_id=None,
            created_at=datetime.now(UTC),
            applied_at=None,
            last_error_code=None,
            **deepcopy(values),
        )
        store["actions"][row.id] = row
        return row

    async def get_action(session, key, *, lock=False):
        """대역 조치를 ID로 조회한다."""
        return store["actions"].get(key)

    async def action_key(session, key):
        """대역 조치의 멱등 키를 조회한다."""
        return next(
            (row for row in store["actions"].values() if row.idempotency_key == key),
            None,
        )

    async def cancel(session, key):
        """대역 조치의 취소 상태를 저장한다."""
        store["actions"][key].status = "cancelled"
        return store["actions"][key]

    monkeypatch.setattr(
        ValidationServiceUtil.IdentityQueryService, "require_active_user", active
    )
    monkeypatch.setattr(
        ValidationServiceUtil.IdentityQueryService, "require_admin", administrative
    )
    monkeypatch.setattr(
        ReportsCommandService.IdentityQueryService, "get_reportable_user", target_user
    )
    for module in (
        ReportsCommandService,
        AssessmentsCommandService,
        ActionsCommandService,
    ):
        monkeypatch.setattr(module, "lock_key", lock)
    monkeypatch.setattr(ReviewRepository, "create_admin_audit", audit)
    for name, function in {
        "create_report": create_report,
        "get_report": get_report,
        "get_report_by_key": report_key,
        "update_report_intake": change_intake,
        "create_assessment": create_assessment,
        "get_assessment": get_assessment,
        "get_assessment_by_key": assessment_key,
        "get_superseding_assessment": successor,
        "get_report_assessment_id": report_assessment,
        "get_active_reversal_id": active_reversal,
        "create_action": create_action,
        "get_action": get_action,
        "get_action_by_key": action_key,
        "cancel_action": cancel,
    }.items():
        monkeypatch.setattr(ReviewRepository, name, function)
    return SimpleNamespace(
        session=Session(), store=store, user=user, admin=admin, other=other
    )


def report_command(target=None):
    """유효한 독립 신고 입력을 만든다."""
    return Types.SubmitReportCommand(
        request_key=uuid4(),
        target_type="user",
        target_id=target or uuid4(),
        reason_code="abuse",
        reason_detail="신고 설명",
    )


def assessment_command(report, **kwargs):
    """동일 대상 신고를 근거로 하는 수동 위반 평가 입력을 만든다."""
    return Types.RecordAssessmentCommand(
        evaluation_key=str(uuid4()),
        target_type=report.target_type,
        target_id=report.target_id,
        policy_version="manual-v1",
        outcome="violation",
        violation_code="abuse",
        rationale="증거 확인",
        reports=(Types.ReportDisposition(report.id, "supported"),),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_report_retry_redaction_and_authorization(memory_backend):
    """원본 재검증 없이 재사용하고 타인·비활성 사용자 조회를 거절한다."""
    b = memory_backend
    command = report_command()
    report = await ReportsCommandService.submit_report(b.session, command, actor=b.user)
    assert (
        await ReportsCommandService.submit_report(b.session, command, actor=b.user)
        == report
    )
    assert len(b.store["reports"]) == 1
    assert not hasattr(report, "evidence_snapshot") and not hasattr(
        report, "intake_reason"
    )
    with pytest.raises(Types.ModerationError, match="idempotency_conflict"):
        await ReportsCommandService.submit_report(
            b.session, replace(command, reason_detail="다른 신고"), actor=b.user
        )
    with pytest.raises(Types.ModerationError, match="not_found"):
        await ReportsQueryService.get_own_report(
            b.session, Types.GetReportCommand(report.id), actor=b.other
        )
    with pytest.raises(Types.ModerationError, match="forbidden"):
        await ReportsQueryService.get_admin_report(
            b.session, Types.GetReportCommand(report.id), actor=b.user
        )
    with pytest.raises(Types.ModerationError, match="forbidden"):
        await ReportsCommandService.submit_report(
            b.session, report_command(), actor=Types.ActorCommand(uuid4())
        )
    info = await ReportsQueryService.get_admin_report(
        b.session, Types.GetReportCommand(report.id), actor=b.admin
    )
    info.evidence_snapshot["server"].clear()
    assert b.store["reports"][report.id].evidence_snapshot["server"]


@pytest.mark.asyncio
async def test_intake_links_state_and_legacy(memory_backend):
    """중복 순환·대상 불일치와 legacy 완료 건 편집을 거절한다."""
    b = memory_backend
    first = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    second = await ReportsCommandService.submit_report(
        b.session, report_command(first.target_id), actor=b.other
    )
    command = Types.ChangeReportIntakeCommand(
        report_id=first.id,
        intake_status="duplicate",
        duplicate_of_report_id=second.id,
        reason="동일 사건",
    )
    result = await ReportsCommandService.change_report_intake(
        b.session, command, actor=b.admin
    )
    assert result.intake_status == "duplicate"
    assert (
        await ReportsCommandService.change_report_intake(
            b.session, command, actor=b.admin
        )
        == result
    )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await ReportsCommandService.change_report_intake(
            b.session,
            replace(command, report_id=second.id, duplicate_of_report_id=first.id),
            actor=b.admin,
        )
    third = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await ReportsCommandService.change_report_intake(
            b.session, replace(command, report_id=third.id), actor=b.admin
        )
    b.store["reports"][third.id].evidence_snapshot["legacy_moderation_flag"] = {
        "status": "reviewed"
    }
    with pytest.raises(Types.ModerationError, match="state_conflict"):
        await ReportsCommandService.change_report_intake(
            b.session,
            Types.ChangeReportIntakeCommand(
                report_id=third.id, intake_status="rejected", reason="거절"
            ),
            actor=b.admin,
        )


@pytest.mark.asyncio
async def test_assessment_retry_rollback_reassessment_and_legacy(memory_backend):
    """근거 불일치 시 평가를 남기지 않고 재평가 분기 및 legacy 오인을 막는다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    command = assessment_command(report)
    result = await AssessmentsCommandService.record_manual_assessment(
        b.session, command, actor=b.admin
    )
    repeated = replace(command, reports=command.reports + command.reports)
    assert (
        await AssessmentsCommandService.record_manual_assessment(
            b.session, repeated, actor=b.admin
        )
        == result
    )
    with pytest.raises(Types.ModerationError, match="idempotency_conflict"):
        await AssessmentsCommandService.record_manual_assessment(
            b.session, replace(command, rationale="다른 판단"), actor=b.admin
        )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await AssessmentsCommandService.record_manual_assessment(
            b.session,
            replace(command, evaluation_key=str(uuid4()), target_id=uuid4()),
            actor=b.admin,
        )
    assert len(b.store["assessments"]) == 1
    next_command = replace(
        command,
        evaluation_key=str(uuid4()),
        supersedes_assessment_id=result.id,
        rationale="재검토",
    )
    next_result = await AssessmentsCommandService.record_manual_assessment(
        b.session, next_command, actor=b.admin
    )
    assert next_result.supersedes_assessment_id == result.id
    with pytest.raises(Types.ModerationError, match="state_conflict"):
        await AssessmentsCommandService.record_manual_assessment(
            b.session, replace(next_command, evaluation_key=str(uuid4())), actor=b.admin
        )
    b.store["reports"][report.id].evidence_snapshot["legacy_moderation_flag"] = {
        "status": "dismissed"
    }
    legacy_command = replace(command, evaluation_key=str(uuid4()))
    with pytest.raises(
        Types.ModerationError, match="legacy_review_acknowledgement_required"
    ):
        await AssessmentsCommandService.record_manual_assessment(
            b.session, legacy_command, actor=b.admin
        )
    assert (
        await AssessmentsCommandService.record_manual_assessment(
            b.session,
            replace(legacy_command, acknowledge_legacy_review=True),
            actor=b.admin,
        )
    ).outcome == "violation"
    with pytest.raises(Types.ModerationError, match="automatic_assessment_disabled"):
        await AssessmentsCommandService.record_automatic_assessment(b.session, command)


@pytest.mark.asyncio
async def test_action_request_cancel_revoke_and_owner_relation(
    memory_backend, monkeypatch
):
    """조치를 pending으로만 저장하고 취소·해제·소유자 관계를 검증한다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    assessment = await AssessmentsCommandService.record_manual_assessment(
        b.session, assessment_command(report), actor=b.admin
    )
    command = Types.RequestActionCommand(
        assessment_id=assessment.id,
        target_type="user",
        target_id=report.target_id,
        action_type="suspend",
        scope="login",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(days=7),
        idempotency_key=uuid4(),
    )
    result = await ActionsCommandService.request_action(
        b.session, command, actor=b.admin
    )
    assert result.status == "pending" and result.applied_at is None
    assert (
        await ActionsCommandService.request_action(b.session, command, actor=b.admin)
        == result
    )
    with pytest.raises(Types.ModerationError, match="idempotency_conflict"):
        await ActionsCommandService.request_action(
            b.session, replace(command, scope="publish"), actor=b.admin
        )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await ActionsCommandService.request_action(
            b.session,
            replace(command, target_id=uuid4(), idempotency_key=uuid4()),
            actor=b.admin,
        )
    revoke = replace(
        command,
        action_type="revoke",
        ends_at=None,
        reverses_action_id=result.id,
        idempotency_key=uuid4(),
    )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await ActionsCommandService.request_action(b.session, revoke, actor=b.admin)
    b.store["actions"][result.id].status = "applied"
    assert (
        await ActionsCommandService.request_action(b.session, revoke, actor=b.admin)
    ).status == "pending"
    with pytest.raises(Types.ModerationError, match="state_conflict"):
        await ActionsCommandService.cancel_pending_action(
            b.session, Types.CancelActionCommand(result.id), actor=b.admin
        )
    pending = await ActionsCommandService.request_action(
        b.session, replace(command, idempotency_key=uuid4()), actor=b.admin
    )
    cancelled = await ActionsCommandService.cancel_pending_action(
        b.session, Types.CancelActionCommand(pending.id), actor=b.admin
    )
    assert cancelled.status == "cancelled"
    assert (
        await ActionsCommandService.cancel_pending_action(
            b.session, Types.CancelActionCommand(pending.id), actor=b.admin
        )
        == cancelled
    )

    # 작품 평가로 무관한 사용자 조치를 요청하지 못한다.
    product_id = uuid4()
    b.store["assessments"][assessment.id].entity.target_type = "product"
    b.store["assessments"][assessment.id].entity.target_id = product_id

    async def product_state(session, command):
        """검증 가능한 작품 소유자 대역을 반환한다."""
        return SimpleNamespace(owner_id=b.user.user_id)

    monkeypatch.setattr(
        ActionsCommandService.ProductQueryService, "get_product_state", product_state
    )
    with pytest.raises(Types.ModerationError, match="invalid_link"):
        await ActionsCommandService.request_action(
            b.session,
            replace(command, idempotency_key=uuid4(), target_id=b.other.user_id),
            actor=b.admin,
        )
    assert (
        await ActionsCommandService.request_action(
            b.session,
            replace(command, idempotency_key=uuid4(), target_id=b.user.user_id),
            actor=b.admin,
        )
    ).status == "pending"


@pytest.mark.parametrize(
    "change",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"target_type": "user"},
        {"cursor": Types.Cursor(datetime.now(UTC).replace(tzinfo=None), uuid4())},
    ],
)
def test_invalid_cursor_and_page(change):
    """잘못된 페이지 입력을 조용히 보정하지 않고 거절한다."""
    with pytest.raises(Types.ModerationError, match="invalid_input"):
        ValidationServiceUtil.validate_page(Types.ListReportsCommand(**change))


@pytest.mark.parametrize(
    "score", [Decimal("NaN"), Decimal("Infinity"), Decimal("-0.1"), Decimal("1.1")]
)
def test_invalid_assessment_scores(score):
    """비유한·범위 밖 신뢰도를 저장 전에 거절한다."""
    with pytest.raises(Types.ModerationError, match="invalid_input"):
        AssessmentsCommandService._normalize_assessment(
            assessment_command(
                SimpleNamespace(id=uuid4(), target_type="user", target_id=uuid4()),
                confidence_score=score,
            )
        )


@pytest.mark.asyncio
async def test_product_snapshot_capture_and_retry_preserves_evidence(
    memory_backend, monkeypatch
):
    """공개 도메인 조회 계약으로 버전 소속을 검사하고 변경된 원본을 재호출에 반영하지 않는다."""
    b = memory_backend
    product_id, snapshot_id, owner_id = uuid4(), uuid4(), uuid4()
    calls = []

    async def accessible(session, command):
        """실제 접근 검증 계약에 신고자와 잠금 옵션이 전달되는지 확인한다."""
        assert command.user_id == b.user.user_id and command.lock is True
        calls.append(command)
        return SimpleNamespace(
            id=product_id, owner_id=owner_id, latest_snapshot_id=snapshot_id
        )

    async def snapshot(session, command):
        """주어진 버전이 타 작품일 때 소속 불일치 대역을 반환한다."""
        return SimpleNamespace(
            id=command.snapshot_id,
            product_id=product_id if command.snapshot_id == snapshot_id else uuid4(),
            version=1,
            snapshot_data={"product": {"title": "발행 제목"}},
        )

    monkeypatch.setattr(
        ReportsCommandService.ProductQueryService, "get_accessible_product", accessible
    )
    monkeypatch.setattr(
        ReportsCommandService.ProductQueryService, "ensure_snapshot_available", snapshot
    )
    command = Types.SubmitReportCommand(
        request_key=uuid4(),
        target_type="product",
        target_id=product_id,
        reason_code="abuse",
    )
    report = await ReportsCommandService.submit_report(b.session, command, actor=b.user)
    admin_info = await ReportsQueryService.get_admin_report(
        b.session, Types.GetReportCommand(report.id), actor=b.admin
    )
    assert (
        admin_info.target_snapshot_id == snapshot_id
        and admin_info.target_owner_user_id == owner_id
    )
    assert admin_info.evidence_snapshot["server"]["title"] == "발행 제목"
    assert (
        await ReportsCommandService.submit_report(b.session, command, actor=b.user)
        == report
    )
    assert len(calls) == 1
    with pytest.raises(Types.ModerationError, match="target_unavailable"):
        await ReportsCommandService.submit_report(
            b.session,
            replace(command, request_key=uuid4(), target_snapshot_id=uuid4()),
            actor=b.user,
        )


@pytest.mark.asyncio
async def test_query_policies_redaction_and_retry_filters(memory_backend, monkeypatch):
    """페이지 조회도 본인 범위를 전달하고 재시도 상태를 강제로 제한한다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )

    async def reports(session, command, *, reporter_id=None):
        """저장소에 사용자 스코프가 전달되는지 확인한다."""
        assert reporter_id == b.user.user_id
        assert command.include_legacy_reviewed is True
        return ReviewRepository.PageRow([b.store["reports"][report.id]], None)

    async def actions(session, command):
        """재시도 조회가 호출자가 준 상태를 무시하고 대기·실패만 선택하는지 확인한다."""
        assert command.statuses == ("pending", "failed")
        return ReviewRepository.PageRow([], None)

    monkeypatch.setattr(ReviewRepository, "list_reports", reports)
    monkeypatch.setattr(ReviewRepository, "list_actions", actions)
    result = await ReportsQueryService.list_own_reports(
        b.session, Types.ListReportsCommand(), actor=b.user
    )
    assert result.items == (report,) and not hasattr(result.items[0], "attachment_refs")
    assert not (
        await ActionsQueryService.list_retry_actions(
            b.session, Types.ListActionsCommand(statuses=("applied",)), actor=b.admin
        )
    ).items


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["report", "assessment", "action"])
async def test_repository_cursor_uses_actual_timestamp_column(kind):
    """각 테이블의 다른 시각 이름을 커서로 사용하고 동률 ID 필터를 SQL에 포함한다."""
    from app.db.models.moderation_review import (
        ModerationAction,
        ModerationAssessment,
        ModerationReport,
    )
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql

    models = {
        "report": (ModerationReport, "received_at"),
        "assessment": (ModerationAssessment, "evaluated_at"),
        "action": (ModerationAction, "created_at"),
    }
    model, field = models[kind]
    now = datetime.now(UTC)
    rows = [SimpleNamespace(id=uuid4(), **{field: now}) for _ in range(2)]

    class Session:
        async def scalars(self, stmt):
            """실제 생성된 SQL에 시각·ID·limit 조건이 있는지 검사한다."""
            sql = str(stmt.compile(dialect=postgresql.dialect()))
            assert f"{field} <" in sql and "id <" in sql and "LIMIT" in sql
            return SimpleNamespace(all=lambda: rows)

    page = await ReviewRepository._fetch_review_page(
        Session(),
        select(model),
        created_at=getattr(model, field),
        id_column=model.id,
        cursor=Types.Cursor(now, uuid4()),
        limit=1,
        cursor_from_entity=lambda item: Types.Cursor(getattr(item, field), item.id),
    )
    assert page.next_cursor == Types.Cursor(now, rows[0].id)


@pytest.mark.asyncio
async def test_persistence_preserves_json_and_isolates_nested_values(memory_backend):
    """알 수 없는 legacy JSON·첨부·권고도 손실 없이 복사하고 ORM 대역과 격리한다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    entity = b.store["reports"][report.id]
    legacy = {"status": "dismissed", "reviewed_by": None, "future": [True, 1, None]}
    entity.evidence_snapshot["legacy_moderation_flag"] = legacy
    entity.attachment_refs = [{"unknown": [False, 0, "", None, {}]}]
    info = PersistenceMapper.report_entity_to_info(entity)
    assert info.evidence_snapshot == entity.evidence_snapshot
    assert info.attachment_refs == entity.attachment_refs
    assert (
        PersistenceMapper.report_info_to_summary(info).legacy_review_status
        == "dismissed"
    )
    assert ValidationServiceUtil.legacy_review_status(info) == "dismissed"
    info.evidence_snapshot["legacy_moderation_flag"]["future"].append("changed")
    info.attachment_refs[0]["unknown"].clear()
    assert legacy["future"] == [True, 1, None]
    assert entity.attachment_refs[0]["unknown"] == [False, 0, "", None, {}]

    assessment = await AssessmentsCommandService.record_manual_assessment(
        b.session,
        replace(assessment_command(report), acknowledge_legacy_review=True),
        actor=b.admin,
    )
    row = b.store["assessments"][assessment.id]
    row.entity.signals["future"] = {"nested": [True, 1, None]}
    row.entity.recommended_actions = [{"unknown": ["keep", None]}]
    info = PersistenceMapper.assessment_row_to_info(row)
    assert info.signals == row.entity.signals
    assert info.recommended_actions == row.entity.recommended_actions
    info.signals["future"]["nested"].clear()
    info.recommended_actions[0]["unknown"].clear()
    assert row.entity.signals["future"]["nested"] == [True, 1, None]
    assert row.entity.recommended_actions[0]["unknown"] == ["keep", None]


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [{}, {"status": None}, {"status": ""}])
async def test_legacy_status_keeps_missing_null_and_empty(memory_backend, legacy):
    """legacy status의 누락·null·빈 문자열을 기본 상태로 합치지 않는다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    entity = b.store["reports"][report.id]
    entity.evidence_snapshot["legacy_moderation_flag"] = legacy
    info = PersistenceMapper.report_entity_to_info(entity)
    assert PersistenceMapper.report_info_to_summary(
        info
    ).legacy_review_status == legacy.get("status")
    assert ValidationServiceUtil.legacy_review_status(info) == legacy.get("status")
    del entity.evidence_snapshot["legacy_moderation_flag"]
    assert (
        PersistenceMapper.report_info_to_summary(
            PersistenceMapper.report_entity_to_info(entity)
        ).legacy_review_status
        is None
    )


def test_empty_pages_and_missing_entities_keep_distinct_results():
    """단건 미존재는 None이며 빈 페이지는 항목 없이 커서를 유지한다."""
    assert PersistenceMapper.report_entity_to_info(None) is None
    assert PersistenceMapper.assessment_row_to_info(None) is None
    assert PersistenceMapper.action_entity_to_info(None) is None
    cursor = Types.Cursor(datetime.now(UTC), uuid4())
    row = ReviewRepository.PageRow([], cursor)
    for page in (
        PersistenceMapper.reports_row_to_page(row),
        PersistenceMapper.reports_row_to_page(row, summary=True),
        PersistenceMapper.assessments_row_to_page(row),
        PersistenceMapper.actions_row_to_page(row),
    ):
        assert page.items == () and page.next_cursor == cursor
    with pytest.raises(Types.ModerationError, match="not_found"):
        ValidationServiceUtil.require_info(None)


@pytest.mark.asyncio
async def test_explicit_null_legacy_object_is_not_treated_as_missing(memory_backend):
    """이관 object의 명시적 null을 누락 기본값으로 바꾸거나 숨기지 않는다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    entity = b.store["reports"][report.id]
    entity.evidence_snapshot["legacy_moderation_flag"] = None
    info = PersistenceMapper.report_entity_to_info(entity)
    with pytest.raises(AttributeError):
        PersistenceMapper.report_info_to_summary(info)
    with pytest.raises(AttributeError):
        ValidationServiceUtil.legacy_review_status(info)


def test_request_fingerprints_match_original_storage_contract():
    """변경 전 구현에서 추출한 세 요청의 SHA256과 UTC·Decimal 정규화를 보존한다."""
    report = Types.SubmitReportCommand(
        request_key=UUID(int=1),
        target_type="user",
        target_id=UUID(int=2),
        reason_code="abuse",
        occurred_at=datetime(2026, 10, 28, tzinfo=UTC),
        form_elapsed_ms=0,
        attachment_claims=("proof",),
    )
    expected = "b3ac2f0c33397f72a24cdbb1cb6e14d13148b11f113fc1790a32ba6229eb30fe"
    assert (
        ValidationServiceUtil.request_fingerprint(report, actor_id=UUID(int=3))
        == expected
    )
    assert (
        ValidationServiceUtil.request_fingerprint(
            replace(
                report,
                occurred_at=datetime(
                    2026, 10, 28, 9, tzinfo=timezone(timedelta(hours=9))
                ),
            ),
            actor_id=UUID(int=3),
        )
        == expected
    )
    for change in (
        {"reason_detail": ""},
        {"form_elapsed_ms": False},
        {"form_elapsed_ms": None},
    ):
        assert (
            ValidationServiceUtil.request_fingerprint(
                replace(report, **change), actor_id=UUID(int=3)
            )
            != expected
        )

    assessment = Types.RecordAssessmentCommand(
        evaluation_key="manual-key",
        target_type="user",
        target_id=UUID(int=2),
        policy_version="v1",
        outcome="violation",
        rationale="review",
        reports=(Types.ReportDisposition(UUID(int=4), "supported"),),
        confidence_score=Decimal("0.5000"),
        violation_code="abuse",
        severity=0,
    )
    expected = "3dfc99d8de38c579f660e25324b85d565af470706c98618f988d68de1d8d56d5"
    assert (
        ValidationServiceUtil.request_fingerprint(assessment, actor_id=UUID(int=3))
        == expected
    )
    assert (
        ValidationServiceUtil.request_fingerprint(
            replace(assessment, confidence_score=Decimal("0.5")), actor_id=UUID(int=3)
        )
        == expected
    )
    action = Types.RequestActionCommand(
        assessment_id=UUID(int=5),
        target_type="user",
        target_id=UUID(int=2),
        action_type="warn",
        scope="login",
        starts_at=datetime(2026, 10, 28, tzinfo=UTC),
        idempotency_key=UUID(int=6),
    )
    assert ValidationServiceUtil.request_fingerprint(action) == (
        "ac2e1bc70e8624e372b7e5a3b44b48343acf0fe1a16c6659231fb3898cf29843"
    )


@pytest.mark.parametrize("value", [None, "", "   ", False, 0, [], {}])
def test_text_validator_checks_runtime_values(value):
    """타입 주석과 무관하게 잘못된 런타임 텍스트를 거절한다."""
    with pytest.raises(Types.ModerationError, match="invalid_input"):
        ValidationServiceUtil.validate_text(value)


def test_time_validator_optional_none_and_original_return_contract():
    """선택적 None만 허용하고 검증 함수는 값을 변환하거나 새 값을 반환하지 않는다."""
    assert ValidationServiceUtil.validate_time(None) is None
    assert (
        ValidationServiceUtil.validate_time(datetime.now(UTC), optional=False) is None
    )
    assert ValidationServiceUtil.validate_text("  keep  ") is None
    with pytest.raises(Types.ModerationError, match="invalid_input"):
        ValidationServiceUtil.validate_time(None, optional=False)


@pytest.mark.parametrize(
    ("start_offset", "end_offset", "valid"),
    [
        (None, None, True),
        (None, 1, False),
        (0, None, False),
        (1, 0, False),
        (0, 0, False),
        (0, 1, True),
    ],
)
def test_assessment_window_pair_contract(start_offset, end_offset, valid):
    """기간을 모두 생략하거나 순서가 맞는 쌍으로만 허용한다."""
    now = datetime(2026, 10, 28, tzinfo=UTC)
    command = assessment_command(
        SimpleNamespace(id=uuid4(), target_type="user", target_id=uuid4()),
        window_start=None
        if start_offset is None
        else now + timedelta(hours=start_offset),
        window_end=None if end_offset is None else now + timedelta(hours=end_offset),
    )
    if valid:
        assert AssessmentsCommandService._normalize_assessment(command) == command
    else:
        with pytest.raises(Types.ModerationError, match="invalid_input"):
            AssessmentsCommandService._normalize_assessment(command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("received_offset", "valid"), [(-1, False), (0, True), (1, True), (2, False)]
)
async def test_assessment_report_window_is_half_open(
    memory_backend, received_offset, valid
):
    """신고 접수 시각에 [start, end)를 적용하며 기간 밖이면 평가를 쓰지 않는다."""
    b = memory_backend
    report = await ReportsCommandService.submit_report(
        b.session, report_command(), actor=b.user
    )
    start = datetime(2026, 10, 28, tzinfo=UTC)
    b.store["reports"][report.id].received_at = start + timedelta(hours=received_offset)
    command = assessment_command(
        report, window_start=start, window_end=start + timedelta(hours=2)
    )
    if valid:
        assessment = await AssessmentsCommandService.record_manual_assessment(
            b.session, command, actor=b.admin
        )
        assert assessment.reports == command.reports
        assert assessment.window_start == start
        assert assessment.window_end == start + timedelta(hours=2)
    else:
        with pytest.raises(Types.ModerationError, match="invalid_link"):
            await AssessmentsCommandService.record_manual_assessment(
                b.session, command, actor=b.admin
            )
        assert not b.store["assessments"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot_data", "expected"),
    [
        (
            {"title": "published", "description": None, "opening_message": ""},
            {"title": "published", "description": None, "opening_message": ""},
        ),
        (
            {"title": "outer", "product": {"title": "", "description": "detail"}},
            {"title": "", "description": "detail", "opening_message": None},
        ),
        (
            {"title": "outer", "product": {}},
            {"title": None, "description": None, "opening_message": None},
        ),
        ({"title": "outer", "product": None}, None),
        ({"title": "outer", "product": []}, None),
    ],
)
async def test_report_snapshot_json_forms_preserve_existing_behavior(
    memory_backend, monkeypatch, snapshot_data, expected
):
    """평면/중첩 증거의 누락·빈 값을 유지하고 손상 구조를 정상 값으로 대체하지 않는다."""
    b = memory_backend
    product_id, snapshot_id = uuid4(), uuid4()

    async def accessible(session, command):
        """신고 대상 접근 서비스의 최소 공개 결과를 반환한다."""
        assert command.lock is True and command.user_id == b.user.user_id
        return SimpleNamespace(
            id=product_id, owner_id=b.user.user_id, latest_snapshot_id=snapshot_id
        )

    async def snapshot(session, command):
        """소속과 버전이 확인된 JSON snapshot을 반환한다."""
        return SimpleNamespace(
            id=snapshot_id,
            product_id=product_id,
            version=1,
            snapshot_data=snapshot_data,
        )

    monkeypatch.setattr(
        ReportsCommandService.ProductQueryService, "get_accessible_product", accessible
    )
    monkeypatch.setattr(
        ReportsCommandService.ProductQueryService, "ensure_snapshot_available", snapshot
    )
    command = replace(report_command(product_id), target_type="product")
    if expected is None:
        with pytest.raises(AttributeError):
            await ReportsCommandService.submit_report(b.session, command, actor=b.user)
        assert not b.store["reports"]
    else:
        report = await ReportsCommandService.submit_report(
            b.session, command, actor=b.user
        )
        info = await ReportsQueryService.get_admin_report(
            b.session, Types.GetReportCommand(report.id), actor=b.admin
        )
        assert info.evidence_snapshot["server"] == {
            "snapshot_id": str(snapshot_id),
            "version": 1,
            **expected,
        }
