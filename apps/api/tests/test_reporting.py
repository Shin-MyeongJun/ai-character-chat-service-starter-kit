"""영역 권한·결과 분리·커버리지·기간·SQL 스코프를 DB 대역과 순수 값으로 검증한다."""

import ast
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.reporting import ReportingError, get_reporting_period
from app.modules.chatting.chat import repository as ChatRepository
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.mapper import reporting as ProductReportingMapper
from app.modules.content.product.repository import (
    reporting as ProductReportingRepository,
)
from app.modules.content.product.service.query import (
    reporting as ProductReportingQueryService,
)
from app.modules.reporting.account_reporting import types as AccountTypes
from app.modules.reporting.account_reporting.service import views as AccountViewsService
from app.modules.reporting.creator_reporting import types as CreatorTypes
from app.modules.reporting.creator_reporting.service import views as CreatorViewsService
from app.modules.reporting.operations_reporting import types as OperationsTypes
from app.modules.reporting.operations_reporting.service import (
    views as OperationsViewsService,
)
from sqlalchemy.dialects import postgresql


def metric_row(day, *, updated_at=None, **counts):
    """허용된 집계 필드와 민감 매출 더미를 가진 저장소 대역을 만든다."""
    fields = dict.fromkeys(ProductReportingMapper.COUNTERS, 0)
    fields.update(counts)
    return SimpleNamespace(
        day=day,
        active_users=2,
        updated_at=updated_at or datetime(2026, 10, 15, tzinfo=UTC),
        revenue={"secret": "hidden"},
        **fields,
    )


def product_command(start, end=None, snapshot_id=None):
    """작품 reporting 입력을 생성한다."""
    return ProductTypes.GetReportingStatisticsCommand(
        actor_id=uuid4(),
        product_id=uuid4(),
        date_from=start,
        date_to=end or start,
        snapshot_id=snapshot_id,
    )


def test_period_seoul_boundaries_and_inclusive_limit():
    """서울 자정과 최대 731일 포함 범위를 검증한다."""
    day = date(2026, 10, 15)
    period = get_reporting_period(day, day)
    assert period.start == datetime(2026, 10, 14, 15, tzinfo=UTC)
    assert period.end == datetime(2026, 10, 15, 15, tzinfo=UTC)
    assert get_reporting_period(day, day + timedelta(days=730))
    for start, end in [
        (day, day + timedelta(days=731)),
        (day, day - timedelta(days=1)),
        (datetime.now(UTC), day),
        (day, date.max),
        (date.min, date.min),
    ]:
        with pytest.raises(ReportingError, match="invalid_period"):
            get_reporting_period(start, end)


def test_product_missing_empty_zero_and_pending_are_distinct():
    """미집계는 None이고 실제 0은 집계 행으로 확인하며 dirty 합계는 확정하지 않는다."""
    day = date(2026, 10, 15)
    command = product_command(day)
    empty = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow([], [], 0, []), command
    )
    assert (
        empty.state == "empty"
        and empty.totals is None
        and empty.recorded_totals is None
    )
    assert empty.days[0].metrics is None and empty.missing_days == (day,)
    row = metric_row(day)
    zero = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow([row], [row], 0, []), command
    )
    assert zero.state == "complete" and zero.totals.succeeded == 0
    dirty = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow([row], [row], 0, [day]), command
    )
    assert (
        dirty.state == "pending"
        and dirty.totals is None
        and dirty.recorded_totals.succeeded == 0
    )
    partial = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow([row], [row], 1, []),
        product_command(day, day + timedelta(days=1)),
    )
    assert (
        partial.state == "partial"
        and partial.totals is None
        and partial.recorded_totals.active_users == 1
    )


def test_version_zero_and_period_unique_users_and_update_range():
    """부모 집계로 무활동 버전의 0을 확인하고 일별 사용자 수를 더하지 않는다."""
    day = date(2026, 10, 15)
    old = datetime(2026, 10, 16, tzinfo=UTC)
    new = old + timedelta(hours=2)
    rows = [
        metric_row(day, updated_at=old, succeeded=2, failed=1, messages=5),
        metric_row(
            day + timedelta(days=1), updated_at=new, succeeded=3, stale=1, messages=4
        ),
    ]
    command = product_command(day, day + timedelta(days=1))
    info = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow(rows, rows, 2, []), command
    )
    assert (
        info.totals.active_users == 2
        and info.totals.succeeded == 5
        and info.totals.messages == 9
    )
    assert info.oldest_updated_at == old and info.newest_updated_at == new
    version = ProductReportingMapper.product_reporting_row_to_info(
        ProductReportingRepository.ProductReportingRow([], rows, 0, []),
        product_command(day, day + timedelta(days=1), uuid4()),
    )
    assert version.totals.active_users == 0 and version.totals.succeeded == 0


@pytest.fixture
def reporting_backend(monkeypatch):
    """인가·도메인 조회를 대역으로 분리해 외부 결과의 노출 경계를 검사한다."""
    ids = {name: uuid4() for name in ("user", "other", "admin", "suspended", "banned")}
    session = SimpleNamespace(no_autoflush=nullcontext())
    calls = []

    async def active(session, command):
        """활성 사용자만 통과시키는 identity 대역이다."""
        if command.user_id not in {ids["user"], ids["other"], ids["admin"]}:
            raise LookupError()

    async def admin(session, command):
        """활성 관리자만 통과시키는 identity 대역이다."""
        if command.user_id != ids["admin"]:
            raise LookupError()

    async def generations(session, command):
        """기간과 실제 행위자가 원본 조회에 전달되는지 기록한다."""
        calls.append(command)
        return SimpleNamespace(pending=1, succeeded=2, failed=1, cancelled=0, stale=0)

    async def usage(session, command):
        """생성 코호트와 다른 usage 기록 수를 반환한다."""
        calls.append(command)
        return SimpleNamespace(
            usage_records=1, input_tokens=10, output_tokens=5, recorded_cost_credit=3
        )

    async def owner(session, command):
        """소유자가 아닌 대상 조회를 거절하는 product 공개 대역이다."""
        if command.actor_id != ids["user"]:
            raise LookupError()
        row = metric_row(command.date_from, succeeded=4)
        return ProductReportingMapper.product_reporting_row_to_info(
            ProductReportingRepository.ProductReportingRow([row], [row], 2, []), command
        )

    async def administrative(session, command):
        """관리자 조회 결과도 공통 집계 사실부터 구성한다."""
        row = metric_row(command.date_from, succeeded=4)
        return ProductReportingMapper.product_reporting_row_to_info(
            ProductReportingRepository.ProductReportingRow([row], [row], 2, []), command
        )

    monkeypatch.setattr(
        AccountViewsService.IdentityQueryService, "require_active_user", active
    )
    monkeypatch.setattr(
        AccountViewsService.IdentityQueryService, "require_admin", admin
    )
    monkeypatch.setattr(
        AccountViewsService.ChatGenerationQueryService,
        "get_account_generation_statistics",
        generations,
    )
    monkeypatch.setattr(
        AccountViewsService.BillingQueryService, "get_account_usage_statistics", usage
    )
    monkeypatch.setattr(
        ProductReportingQueryService, "get_owner_reporting_statistics", owner
    )
    monkeypatch.setattr(
        ProductReportingQueryService, "get_admin_reporting_statistics", administrative
    )
    return session, ids, calls


@pytest.mark.asyncio
async def test_account_scope_and_record_count_semantics(reporting_backend):
    """조회 대상을 입력받지 않고 행위자 본인만 원본에 전달한다."""
    session, ids, calls = reporting_backend
    day = date(2026, 10, 15)
    result = await AccountViewsService.get_account_report(
        session,
        AccountTypes.GetAccountReportCommand(day, day),
        actor=AccountTypes.ActorCommand(ids["user"]),
    )
    assert all(command.user_id == ids["user"] for command in calls)
    assert result.generations.succeeded == 2 and result.usage.usage_records == 1
    assert "user_id" not in asdict(result) and not hasattr(result, "revenue")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["suspended", "banned"])
async def test_inactive_users_rejected_everywhere(reporting_backend, name):
    """정지·차단 사용자의 본인·작가·관리자 조회를 모두 차단한다."""
    session, ids, _ = reporting_backend
    day = date(2026, 10, 15)
    for module, command, actor in [
        (
            AccountViewsService,
            AccountTypes.GetAccountReportCommand(day, day),
            AccountTypes.ActorCommand(ids[name]),
        ),
        (
            CreatorViewsService,
            CreatorTypes.GetCreatorProductReportCommand(uuid4(), day, day),
            CreatorTypes.ActorCommand(ids[name]),
        ),
        (
            OperationsViewsService,
            OperationsTypes.GetOperationsProductReportCommand(uuid4(), day, day),
            OperationsTypes.ActorCommand(ids[name]),
        ),
    ]:
        function = (
            module.get_account_report
            if module is AccountViewsService
            else module.get_product_report
        )
        with pytest.raises(ReportingError, match="forbidden"):
            await function(session, command, actor=actor)


@pytest.mark.asyncio
async def test_creator_owner_and_admin_boundaries_and_safe_results(reporting_backend):
    """타 작가·비관리자 접근을 막고 별도 결과에 매출·개인정보를 포함하지 않는다."""
    session, ids, _ = reporting_backend
    day = date(2026, 10, 15)
    creator = CreatorTypes.GetCreatorProductReportCommand(uuid4(), day, day)
    with pytest.raises(ReportingError, match="not_found"):
        await CreatorViewsService.get_product_report(
            session, creator, actor=CreatorTypes.ActorCommand(ids["other"])
        )
    result = await CreatorViewsService.get_product_report(
        session, creator, actor=CreatorTypes.ActorCommand(ids["user"])
    )
    assert result.totals.succeeded == 4
    assert all(
        key not in asdict(result.totals)
        for key in ("revenue", "user_id", "signals", "error_code")
    )
    command = OperationsTypes.GetOperationsProductReportCommand(
        creator.product_id, day, day
    )
    with pytest.raises(ReportingError, match="forbidden"):
        await OperationsViewsService.get_product_report(
            session, command, actor=OperationsTypes.ActorCommand(ids["user"])
        )
    operations = await OperationsViewsService.get_product_report(
        session, command, actor=OperationsTypes.ActorCommand(ids["admin"])
    )
    assert type(operations.totals) is not type(result.totals)


@pytest.mark.asyncio
async def test_account_query_sql_is_scoped_and_half_open():
    """실제 생성된 SQL에 사용자·시작·종료 조건이 포함되는지 검증한다."""
    uid = uuid4()
    period = get_reporting_period(date(2026, 10, 15), date(2026, 10, 15))

    class Session:
        async def execute(self, stmt):
            """실제 SQL 컴파일 결과를 검사하고 빈 집계 행을 반환한다."""
            compiled = stmt.compile(dialect=postgresql.dialect())
            assert (
                "user_id =" in str(compiled)
                and "created_at >=" in str(compiled)
                and "created_at <" in str(compiled)
            )
            assert (
                uid in compiled.params.values()
                and period.end in compiled.params.values()
            )
            return SimpleNamespace(all=list)

    assert (
        await ChatRepository.get_account_generation_statistics(
            Session(), uid, period.start, period.end
        )
        == []
    )


def test_reporting_import_boundaries():
    """영역 간 참조·ORM 접근·역방향 참조를 금지한다."""
    root = Path(__file__).resolve().parents[1] / "app"
    names = {"account_reporting", "creator_reporting", "operations_reporting"}
    for name in names:
        for path in root.joinpath("modules", "reporting", name).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    assert not module.startswith("app.db.models")
                    for other in names - {name}:
                        assert not module.startswith(f"app.modules.reporting.{other}")
                    if module.startswith("app.modules.") and not module.startswith(
                        f"app.modules.reporting.{name}"
                    ):
                        assert "repository" not in module and "mapper" not in module
    for path in root.joinpath("core").rglob("*.py"):
        assert not any(
            f"app.modules.reporting.{name}" in path.read_text(encoding="utf-8") for name in names
        )


@pytest.mark.asyncio
async def test_recorded_service_freshness_and_queue_are_not_claimed_complete(
    reporting_backend, monkeypatch
):
    """관리자 집계 범위와 요청 시각의 한계를 그대로 반환하고 최신 갱신을 완료로 오인하지 않는다."""
    session, ids, _calls = reporting_backend
    day = date(2026, 10, 15)
    old = datetime(2026, 10, 15, tzinfo=UTC)
    new = old + timedelta(hours=1)

    async def recorded(session, command):
        """기간 내 DISTINCT 사용자 1명을 가진 기록된 전체 집계를 반환한다."""
        return ProductTypes.ServiceReportingStatisticsInfo(
            ProductTypes.ReportingMetricsInfo(1, 10, 2, 0, 1, 20, 2, 0, 100, 30, 5),
            3,
            2,
            old,
            new,
            1,
            old,
        )

    async def queue(session, command):
        """미집계 큐를 수정하지 않는 공개 조회 대역이다."""
        return ProductTypes.StatisticsQueueInfo(1, old)

    monkeypatch.setattr(
        ProductReportingQueryService, "get_recorded_service_statistics", recorded
    )
    monkeypatch.setattr(ProductReportingQueryService, "get_statistics_queue", queue)
    actor = OperationsTypes.ActorCommand(ids["admin"])
    result = await OperationsViewsService.get_recorded_service_report(
        session, OperationsTypes.GetRecordedServiceReportCommand(day, day), actor=actor
    )
    assert (
        result.recorded_totals.active_users == 1 and result.freshness.state == "pending"
    )
    assert result.coverage == "all_product_day_coverage_not_verified"
    assert (
        result.freshness.oldest_updated_at == old
        and result.freshness.newest_updated_at == new
    )
    assert not hasattr(result, "completed_at")
    assert (
        await OperationsViewsService.get_statistics_queue_report(session, actor=actor)
    ).pending_product_days == 1


@pytest.mark.asyncio
async def test_storage_failure_is_not_an_empty_report(reporting_backend, monkeypatch):
    """원본 조회 장애를 0건이나 빈 성공 결과로 숨기지 않는다."""
    session, ids, _calls = reporting_backend

    async def broken(session, command):
        """저장소 실패를 재현하는 공개 경계 대역이다."""
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        AccountViewsService.BillingQueryService, "get_account_usage_statistics", broken
    )
    day = date(2026, 10, 15)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await AccountViewsService.get_account_report(
            session,
            AccountTypes.GetAccountReportCommand(day, day),
            actor=AccountTypes.ActorCommand(ids["user"]),
        )


def test_source_account_mappers_use_declared_info_types():
    """생성/사용량 source mapper가 ORM을 노출하지 않고 정확한 계약으로 변환한다."""
    from app.modules.chatting.chat.mapper import persistence as ChatPersistenceMapper
    from app.modules.commerce.billing.mapper import (
        persistence as BillingPersistenceMapper,
    )

    assert (
        ChatPersistenceMapper.account_generation_statistics_rows_to_info(
            [("succeeded", 2)]
        ).succeeded
        == 2
    )
    empty = BillingPersistenceMapper.account_usage_statistics_row_to_info((0, 0, 0, 0))
    assert empty.usage_records == 0 and empty.input_tokens == 0
