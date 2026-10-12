"""Creator 영역의 허용 필드만 구성하는 순수 mapper."""

from dataclasses import fields

from app.core.reporting import FreshnessInfo
from app.modules.creator_reporting import types as Types


def _metrics_info_to_result(info) -> Types.CreatorMetricsInfo | None:
    """매출·사용자 식별자 없이 이 영역의 사용량 필드만 선택한다."""
    return (
        None
        if info is None
        else Types.CreatorMetricsInfo(
            **{
                field.name: getattr(info, field.name)
                for field in fields(Types.CreatorMetricsInfo)
            }
        )
    )


def product_statistics_info_to_view(
    info, period, queried_at
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
