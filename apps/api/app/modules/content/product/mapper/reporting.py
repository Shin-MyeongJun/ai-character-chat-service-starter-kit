"""기존 집계의 존재·미집계·알려진 0을 구분하는 순수 reporting 변환."""

from datetime import date, datetime, timedelta
from typing import Literal, TypeAlias

from app.db.models.product_statistics import ProductDailyStats, ProductVersionDailyStats
from app.modules.content.product import types as Types
from app.modules.content.product.repository.reporting import (
    ProductReportingRow,
    ServiceReportingRow,
    StatisticsQueueRow,
)

_CounterName: TypeAlias = Literal[
    "succeeded",
    "failed",
    "cancelled",
    "stale",
    "messages",
    "conversations",
    "transitions",
    "input_tokens",
    "output_tokens",
    "cost_credit",
]
COUNTERS: tuple[_CounterName, ...] = (
    "succeeded",
    "failed",
    "cancelled",
    "stale",
    "messages",
    "conversations",
    "transitions",
    "input_tokens",
    "output_tokens",
    "cost_credit",
)


def _statistics_entity_to_metrics(
    entity: ProductDailyStats | ProductVersionDailyStats,
) -> Types.ReportingMetricsInfo:
    """단일 일별 집계의 공개 사용량 필드만 선택한다. 매출 JSON은 포함하지 않는다."""
    return Types.ReportingMetricsInfo(
        active_users=entity.active_users,
        succeeded=entity.succeeded,
        failed=entity.failed,
        cancelled=entity.cancelled,
        stale=entity.stale,
        messages=entity.messages,
        conversations=entity.conversations,
        transitions=entity.transitions,
        input_tokens=entity.input_tokens,
        output_tokens=entity.output_tokens,
        cost_credit=entity.cost_credit,
    )


def product_reporting_row_to_info(
    row: ProductReportingRow, command: Types.GetReportingStatisticsCommand
) -> Types.ReportingStatisticsInfo:
    """부모 집계가 있는 버전의 무활동만 0으로 표현하고 미집계 합계를 확정하지 않는다."""
    roots = {item.day: item for item in row.root_rows}
    rows = {item.day: item for item in row.rows}
    pending = tuple(row.pending_days)
    days: list[Types.ReportingDayInfo] = []
    missing: list[date] = []
    updates: list[datetime] = []
    sums: dict[_CounterName, int] = dict.fromkeys(COUNTERS, 0)
    span = (command.date_to - command.date_from).days + 1
    for offset in range(span):
        day = command.date_from + timedelta(days=offset)
        entity = rows.get(day)
        root = roots.get(day)
        if root is None:
            # 없는 집계는 실제 활동이 없었다는 증거가 아니다.
            missing.append(day)
            days.append(
                Types.ReportingDayInfo(
                    day, None, None, "pending" if day in pending else "missing"
                )
            )
            continue
        metrics = (
            _statistics_entity_to_metrics(entity)
            if entity is not None
            else Types.ReportingMetricsInfo(*(0 for _ in range(11)))
        )
        updated_at = entity.updated_at if entity is not None else root.updated_at
        updates.append(updated_at)
        days.append(
            Types.ReportingDayInfo(
                day, metrics, updated_at, "pending" if day in pending else "collected"
            )
        )
        sums["succeeded"] += metrics.succeeded
        sums["failed"] += metrics.failed
        sums["cancelled"] += metrics.cancelled
        sums["stale"] += metrics.stale
        sums["messages"] += metrics.messages
        sums["conversations"] += metrics.conversations
        sums["transitions"] += metrics.transitions
        sums["input_tokens"] += metrics.input_tokens
        sums["output_tokens"] += metrics.output_tokens
        sums["cost_credit"] += metrics.cost_credit
    recorded = (
        Types.ReportingMetricsInfo(
            row.active_users, *(sums[field] for field in COUNTERS)
        )
        if updates
        else None
    )
    state = (
        "pending"
        if pending
        else "empty"
        if not updates
        else "partial"
        if missing
        else "complete"
    )
    return Types.ReportingStatisticsInfo(
        command.product_id,
        command.snapshot_id,
        command.date_from,
        command.date_to,
        recorded,
        recorded if state == "complete" else None,
        tuple(days),
        tuple(missing),
        pending,
        min(updates) if updates else None,
        max(updates) if updates else None,
        state,
    )


def service_reporting_row_to_info(
    row: ServiceReportingRow,
) -> Types.ServiceReportingStatisticsInfo:
    """기록된 전체 집계를 변환하되 서비스 전체 수집 완료를 가정하지 않는다."""
    count, products, oldest, newest, *sums = row.metrics
    pending_count, oldest_requested_at = row.pending
    metrics = (
        Types.ReportingMetricsInfo(row.active_users, *(int(value) for value in sums))
        if count
        else None
    )
    return Types.ServiceReportingStatisticsInfo(
        metrics, count, products, oldest, newest, pending_count, oldest_requested_at
    )


def statistics_queue_row_to_info(row: StatisticsQueueRow) -> Types.StatisticsQueueInfo:
    """대기 작업 raw 집계를 공개 값으로 변환한다."""
    pending_product_days, oldest_requested_at = row
    return Types.StatisticsQueueInfo(pending_product_days, oldest_requested_at)
