"""Operations 영역의 허용 필드만 구성하는 순수 mapper."""

from dataclasses import fields

from app.core.reporting import FreshnessInfo
from app.modules.operations_reporting import types as Types


def _metrics_info_to_result(info) -> Types.OperationsMetricsInfo | None:
    """매출·사용자 식별자 없이 이 영역의 사용량 필드만 선택한다."""
    return (
        None
        if info is None
        else Types.OperationsMetricsInfo(
            **{
                field.name: getattr(info, field.name)
                for field in fields(Types.OperationsMetricsInfo)
            }
        )
    )


def product_statistics_info_to_view(
    info, period, queried_at
) -> Types.OperationsProductReportView:
    """집계된 날짜와 누락·dirty 날짜를 구분해 전체 기간 완료를 과장하지 않는다."""
    days = tuple(
        Types.OperationsDayInfo(
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
    return Types.OperationsProductReportView(
        info.product_id,
        info.snapshot_id,
        period,
        queried_at,
        _metrics_info_to_result(info.totals),
        _metrics_info_to_result(info.recorded_totals),
        days,
        freshness,
    )


def service_statistics_info_to_view(
    info, period, queried_at
) -> Types.RecordedServiceReportView:
    """저장된 작품 집계만 반환하고 전체 서비스 수집 완료 시각을 만들지 않는다."""
    state = (
        "pending"
        if info.pending_product_days
        else "empty"
        if not info.product_days
        else "unverified"
    )
    freshness = FreshnessInfo(
        state,
        info.oldest_updated_at,
        info.newest_updated_at,
        (),
        (),
        "recorded_product_daily_statistics_only",
    )
    return Types.RecordedServiceReportView(
        period,
        queried_at,
        _metrics_info_to_result(info.recorded_totals),
        info.product_days,
        info.products_with_rows,
        info.pending_product_days,
        info.oldest_pending_at,
        freshness,
    )


def statistics_queue_info_to_view(info, queried_at) -> Types.StatisticsQueueReportView:
    """대기 작업 최신 요청 시각의 경과를 계산한다. 최초 적체 시각이라고 주장하지 않는다."""
    age = (
        max(0.0, (queried_at - info.oldest_requested_at).total_seconds())
        if info.oldest_requested_at is not None
        else None
    )
    return Types.StatisticsQueueReportView(
        info.pending_product_days, info.oldest_requested_at, age, queried_at
    )
