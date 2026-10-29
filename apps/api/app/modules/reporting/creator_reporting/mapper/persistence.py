"""Creator 영역의 허용 필드만 구성하는 순수 mapper."""

from datetime import datetime

from app.core.reporting import FreshnessInfo, PeriodInfo
from app.modules.content.product import types as ProductTypes
from app.modules.reporting.creator_reporting import types as Types


def _metrics_info_to_result(
    info: ProductTypes.ReportingMetricsInfo | None,
) -> Types.CreatorMetricsInfo | None:
    """매출·사용자 식별자 없이 이 영역의 사용량 필드만 선택한다."""
    if info is None:
        return None
    return Types.CreatorMetricsInfo(
        active_users=info.active_users,
        succeeded=info.succeeded,
        failed=info.failed,
        cancelled=info.cancelled,
        stale=info.stale,
        messages=info.messages,
        conversations=info.conversations,
        transitions=info.transitions,
        input_tokens=info.input_tokens,
        output_tokens=info.output_tokens,
        cost_credit=info.cost_credit,
    )


def product_statistics_info_to_view(
    info: ProductTypes.ReportingStatisticsInfo,
    period: PeriodInfo,
    queried_at: datetime,
) -> Types.CreatorProductReportView:
    """집계된 날짜와 누락·dirty 날짜를 구분해 전체 기간 완료를 과장하지 않는다."""
    days = tuple(
        Types.CreatorDayInfo(
            day.day, _metrics_info_to_result(day.metrics), day.updated_at, day.state
        )
        for day in info.days
    )
    freshness = FreshnessInfo(
        info.state,
        info.oldest_updated_at,
        info.newest_updated_at,
        info.missing_days,
        info.pending_days,
        "product_daily_statistics",
    )
    return Types.CreatorProductReportView(
        info.product_id,
        info.snapshot_id,
        period,
        queried_at,
        _metrics_info_to_result(info.totals),
        _metrics_info_to_result(info.recorded_totals),
        days,
        freshness,
    )
