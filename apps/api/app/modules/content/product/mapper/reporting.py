"""기존 집계의 존재·미집계·알려진 0을 구분하는 순수 reporting 변환."""

from datetime import timedelta

from app.modules.content.product import types as Types

COUNTERS = (
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


def _statistics_entity_to_metrics(entity) -> Types.ReportingMetricsInfo:
    """단일 일별 집계의 공개 사용량 필드만 선택한다. 매출 JSON은 포함하지 않는다."""
    return Types.ReportingMetricsInfo(
        entity.active_users, *(getattr(entity, field) for field in COUNTERS)
    )


def product_reporting_row_to_info(row, command) -> Types.ReportingStatisticsInfo:
    """부모 집계가 있는 버전의 무활동만 0으로 표현하고 미집계 합계를 확정하지 않는다."""
    roots = {item.day: item for item in row.root_rows}
    rows = {item.day: item for item in row.rows}
    pending = tuple(row.pending_days)
    days, missing, updates = [], [], []
    sums = dict.fromkeys(COUNTERS, 0)
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
        for field in COUNTERS:
            sums[field] += getattr(metrics, field)
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


def service_reporting_row_to_info(row) -> Types.ServiceReportingStatisticsInfo:
    """기록된 전체 집계를 변환하되 서비스 전체 수집 완료를 가정하지 않는다."""
    count, products, oldest, newest, *sums = row.metrics
    metrics = (
        Types.ReportingMetricsInfo(row.active_users, *(int(value) for value in sums))
        if count
        else None
    )
    return Types.ServiceReportingStatisticsInfo(
        metrics, count, products, oldest, newest, row.pending[0], row.pending[1]
    )


def statistics_queue_row_to_info(row) -> Types.StatisticsQueueInfo:
    """대기 작업 raw 집계를 공개 값으로 변환한다."""
    return Types.StatisticsQueueInfo(row[0], row[1])
