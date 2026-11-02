"""Reporting 공개 값의 노출·미집계 의미와 읽기 전용 실행 계약을 검증한다."""

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.reporting import get_reporting_period
from app.modules.chatting.chat import types as ChatTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import types as ProductTypes
from app.modules.reporting.account_reporting import types as AccountTypes
from app.modules.reporting.account_reporting.mapper import persistence as AccountMapper
from app.modules.reporting.account_reporting.service import views as AccountService
from app.modules.reporting.creator_reporting import types as CreatorTypes
from app.modules.reporting.creator_reporting.mapper import persistence as CreatorMapper
from app.modules.reporting.creator_reporting.service import views as CreatorService
from app.modules.reporting.operations_reporting import schemas as OperationsSchemas
from app.modules.reporting.operations_reporting import types as OperationsTypes
from app.modules.reporting.operations_reporting.mapper import (
    persistence as OperationsMapper,
)
from app.modules.reporting.operations_reporting.mapper import prompts as PromptsMapper
from app.modules.reporting.operations_reporting.mapper import schema as SchemaMapper
from app.modules.reporting.operations_reporting.service import prompts as PromptsService
from app.modules.reporting.operations_reporting.service import (
    views as OperationsService,
)

DAY = date(2026, 10, 20)
NOW = datetime(2026, 10, 21, tzinfo=UTC)


@pytest.mark.parametrize("state", ["empty", "partial", "pending", "complete"])
def test_product_projection_preserves_nullable_coverage_and_period_distinct(
    state: str,
) -> None:
    """두 영역 모두 원본 기간 DISTINCT와 일별 0/미집계 및 dirty 값을 보존한다."""
    metrics = ProductTypes.ReportingMetricsInfo(2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    zero = ProductTypes.ReportingMetricsInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    second_day = DAY + timedelta(days=1)
    missing = (second_day,) if state in {"empty", "partial"} else ()
    pending = (DAY,) if state == "pending" else ()
    recorded = None if state == "empty" else metrics
    confirmed = metrics if state == "complete" else None
    info = ProductTypes.ReportingStatisticsInfo(
        product_id=uuid4(),
        snapshot_id=uuid4(),
        date_from=DAY,
        date_to=second_day,
        recorded_totals=recorded,
        totals=confirmed,
        days=(
            ProductTypes.ReportingDayInfo(
                DAY, recorded, NOW if recorded else None, state
            ),
            ProductTypes.ReportingDayInfo(
                second_day,
                None if missing else zero,
                None if missing else NOW,
                "missing" if missing else "recorded",
            ),
        ),
        missing_days=missing,
        pending_days=pending,
        oldest_updated_at=NOW if recorded else None,
        newest_updated_at=NOW if recorded else None,
        state=state,
    )
    period = get_reporting_period(DAY, second_day)
    creator = CreatorMapper.product_statistics_info_to_view(info, period, NOW)
    operations = OperationsMapper.product_statistics_info_to_view(info, period, NOW)
    assert type(creator) is not type(operations)
    for view in (creator, operations):
        assert (
            view.product_id == info.product_id and view.snapshot_id == info.snapshot_id
        )
        assert view.period == period and view.queried_at == NOW
        assert view.freshness.state == state
        assert view.freshness.missing_days == missing
        assert view.freshness.pending_days == pending
        assert (view.totals is None) is (confirmed is None)
        if view.recorded_totals is not None:
            assert asdict(view.recorded_totals) == asdict(metrics)
        else:
            assert recorded is None
        if view.totals is not None:
            assert asdict(view.totals) == asdict(metrics)
        if missing:
            assert view.days[1].metrics is None
        else:
            assert view.days[1].metrics is not None
            assert asdict(view.days[1].metrics) == asdict(zero)


@pytest.mark.parametrize(
    "counter", [None, "pending", "succeeded", "failed", "cancelled", "stale", "usage"]
)
def test_account_empty_requires_both_sources_to_have_no_records(
    counter: str | None,
) -> None:
    """각 생성 상태와 별도 usage 기록을 보존하고 성공 건수와 동일시하지 않는다."""
    generations = ChatTypes.AccountGenerationStatisticsInfo(
        pending=int(counter == "pending"),
        succeeded=int(counter == "succeeded"),
        failed=int(counter == "failed"),
        cancelled=int(counter == "cancelled"),
        stale=int(counter == "stale"),
    )
    usage = BillingTypes.AccountUsageStatisticsInfo(int(counter == "usage"), 0, 0, 0)
    view = AccountMapper.generation_usage_infos_to_view(
        generations, usage, get_reporting_period(DAY, DAY), NOW
    )
    assert view.state == ("empty" if counter is None else "recorded")
    assert asdict(view.generations) == asdict(generations)
    assert view.usage.usage_records == usage.usage_records
    assert view.usage.recorded_cost_credit == 0


@pytest.mark.parametrize(
    "pending,rows,state", [(0, 0, "empty"), (0, 2, "unverified"), (1, 2, "pending")]
)
def test_recorded_service_has_no_confirmed_totals(
    pending: int,
    rows: int,
    state: str,
) -> None:
    """미집계와 기록된 0을 구분하고 전체 서비스의 수집 완료를 주장하지 않는다."""
    metrics = ProductTypes.ReportingMetricsInfo(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    info = ProductTypes.ServiceReportingStatisticsInfo(
        metrics if rows else None,
        rows,
        int(bool(rows)),
        NOW if rows else None,
        NOW if rows else None,
        pending,
        NOW if pending else None,
    )
    view = OperationsMapper.service_statistics_info_to_view(
        info, get_reporting_period(DAY, DAY), NOW
    )
    assert view.freshness.state == state
    assert (view.recorded_totals is None) is (rows == 0)
    assert view.coverage == "all_product_day_coverage_not_verified"
    assert not hasattr(view, "totals") and not hasattr(view, "completed_at")


@pytest.mark.parametrize("recorded", [False, True])
def test_prompt_http_projection_keeps_legacy_serialization_and_nulls(
    recorded: bool,
) -> None:
    """명시 DTO 변환이 기존 직렬화와 같고 목록에 원문을 포함하지 않음을 검증한다."""
    summary = ChatTypes.GenerationPromptSummaryInfo(
        uuid4(),
        uuid4(),
        uuid4(),
        "saved-model",
        "none",
        "failed",
        NOW,
        None,
        None,
        recorded,
        NOW if recorded else None,
        "openai" if recorded else None,
    )
    prompt = (
        ChatTypes.GenerationPromptInfo(
            '{ "messages": [] }\n', "saved-digest", 1, NOW, "openai", 1200
        )
        if recorded
        else None
    )
    detail = PromptsMapper.generation_prompt_detail_info_to_view(
        ChatTypes.GenerationPromptDetailInfo(summary, prompt)
    )
    page = PromptsMapper.generation_prompt_page_info_to_view(
        ChatTypes.GenerationPromptPageInfo((summary,), 9),
        OperationsTypes.ListGenerationPromptsCommand(DAY, DAY, page=2, page_size=3),
    )
    detail_response = SchemaMapper.generation_prompt_detail_view_to_response(detail)
    page_response = SchemaMapper.generation_prompt_page_view_to_response(page)
    # 비교 결과만 assertion에 전달해 실패하더라도 원문을 테스트 출력에 펼치지 않는다.
    same_detail = detail_response.model_dump(mode="json") == (
        OperationsSchemas.GenerationPromptDetailResponseDto(
            **asdict(detail)
        ).model_dump(mode="json")
    )
    same_page = page_response.model_dump(mode="json") == (
        OperationsSchemas.GenerationPromptPageResponseDto(**asdict(page)).model_dump(
            mode="json"
        )
    )
    assert same_detail and same_page
    assert set(page_response.items[0].model_dump()) == set(asdict(summary))
    assert (detail_response.prompt is None) is (not recorded)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "account",
        "creator",
        "operations",
        "service",
        "queue",
        "prompt_list",
        "prompt_detail",
    ],
)
@pytest.mark.parametrize("fails", [False, True])
async def test_all_public_queries_disable_autoflush_and_restore_it(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    fails: bool,
) -> None:
    """실제 세션에서 성공·원본 실패 모두 autoflush를 복구하고 명시 쓰기를 하지 않는다."""
    actor_id, product_id = uuid4(), uuid4()
    target: ModuleType
    facts: object
    if query == "account":
        target = AccountService.ChatGenerationQueryService
        source_name = "get_account_generation_statistics"
        facts = ChatTypes.AccountGenerationStatisticsInfo(0, 0, 0, 0, 0)
    elif query in {"creator", "operations"}:
        target = CreatorService.ProductReportingQueryService
        source_name = (
            "get_owner_reporting_statistics"
            if query == "creator"
            else "get_admin_reporting_statistics"
        )
        facts = ProductTypes.ReportingStatisticsInfo(
            product_id, None, DAY, DAY, None, None, (), (DAY,), (), None, None, "empty"
        )
    elif query == "service":
        target = OperationsService.ProductReportingQueryService
        source_name = "get_recorded_service_statistics"
        facts = ProductTypes.ServiceReportingStatisticsInfo(
            None, 0, 0, None, None, 0, None
        )
    elif query == "queue":
        target = OperationsService.ProductReportingQueryService
        source_name = "get_statistics_queue"
        facts = ProductTypes.StatisticsQueueInfo(0, None)
    else:
        target = PromptsService.ChatPromptsQueryService
        source_name = (
            "list_generation_prompts"
            if query == "prompt_list"
            else "get_generation_prompt"
        )
        summary = ChatTypes.GenerationPromptSummaryInfo(
            uuid4(),
            uuid4(),
            uuid4(),
            "saved-model",
            "none",
            "failed",
            NOW,
            None,
            None,
            False,
            None,
            None,
        )
        facts = (
            ChatTypes.GenerationPromptPageInfo((), 0)
            if query == "prompt_list"
            else ChatTypes.GenerationPromptDetailInfo(summary, None)
        )

    async def require_actor(session: AsyncSession, command: object) -> None:
        assert session.autoflush is False

    async def read_facts(session: AsyncSession, command: object) -> object:
        assert session.autoflush is False
        if fails:
            raise RuntimeError("source unavailable")
        return facts

    identity = AsyncMock(side_effect=require_actor)
    monkeypatch.setattr(
        AccountService.IdentityQueryService, "require_active_user", identity
    )
    monkeypatch.setattr(AccountService.IdentityQueryService, "require_admin", identity)
    monkeypatch.setattr(target, source_name, AsyncMock(side_effect=read_facts))
    monkeypatch.setattr(
        AccountService.BillingQueryService,
        "get_account_usage_statistics",
        AsyncMock(return_value=BillingTypes.AccountUsageStatisticsInfo(0, 0, 0, 0)),
    )
    async with AsyncSession() as session:
        writes = [
            AsyncMock(side_effect=AssertionError("reporting must remain read-only"))
            for _ in range(2)
        ]
        monkeypatch.setattr(session, "flush", writes[0])
        monkeypatch.setattr(session, "commit", writes[1])

        async def read_report() -> object:
            if query == "account":
                return await AccountService.get_account_report(
                    session,
                    AccountTypes.GetAccountReportCommand(DAY, DAY),
                    actor=AccountTypes.ActorCommand(actor_id),
                )
            if query == "creator":
                return await CreatorService.get_product_report(
                    session,
                    CreatorTypes.GetCreatorProductReportCommand(product_id, DAY, DAY),
                    actor=CreatorTypes.ActorCommand(actor_id),
                )
            actor = OperationsTypes.ActorCommand(actor_id)
            if query == "operations":
                return await OperationsService.get_product_report(
                    session,
                    OperationsTypes.GetOperationsProductReportCommand(
                        product_id, DAY, DAY
                    ),
                    actor=actor,
                )
            if query == "service":
                return await OperationsService.get_recorded_service_report(
                    session,
                    OperationsTypes.GetRecordedServiceReportCommand(DAY, DAY),
                    actor=actor,
                )
            if query == "queue":
                return await OperationsService.get_statistics_queue_report(
                    session, actor=actor
                )
            if query == "prompt_list":
                return await PromptsService.list_generation_prompts(
                    session,
                    OperationsTypes.ListGenerationPromptsCommand(DAY, DAY),
                    actor=actor,
                )
            return await PromptsService.get_generation_prompt(
                session,
                OperationsTypes.GetGenerationPromptCommand(uuid4()),
                actor=actor,
            )

        assert session.autoflush is True
        if fails:
            with pytest.raises(RuntimeError, match="source unavailable"):
                await read_report()
        else:
            await read_report()
        assert session.autoflush is True
        identity.assert_awaited_once()
        for write in writes:
            write.assert_not_awaited()
