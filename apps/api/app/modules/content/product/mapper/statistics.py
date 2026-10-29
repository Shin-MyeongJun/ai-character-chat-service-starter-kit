# 생성/대화/버전전환/usage/결제 사실을 통화별 Decimal 집계로 합친다. 환율 변환은 하지 않는다.
# 매출은 문자열로 반환하고 활성 사용자는 성공 생성 사용자의 중복을 제거한다.
from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Literal, TypeAlias, TypedDict
from uuid import UUID

from app.modules.content.product import types as Types
from app.modules.content.product.mapper.persistence import (
    statistics_row_to_day_info,
    statistics_values_to_metrics_info,
)
from app.modules.content.product.repository.statistics import StatisticsReportRow

_GenerationCounter: TypeAlias = Literal["succeeded", "failed", "cancelled", "stale"]
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
# Finished generation facts are accumulated into these existing terminal buckets.
# A pending/unknown status still raises KeyError, rather than being ignored/coerced.
_STATUS_COUNTERS: dict[str, _GenerationCounter] = {
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
    "stale": "stale",
}


class _PaymentBucket(TypedDict):
    sales: Decimal
    refunds: Decimal
    payment_ids: set[UUID]
    refund_count: int


class _PeriodRevenueBucket(TypedDict):
    sales: Decimal
    refunds: Decimal
    net: Decimal
    sale_count: int
    refund_count: int


_MONEY_FIELDS: tuple[Literal["sales", "refunds", "net"], ...] = (
    "sales",
    "refunds",
    "net",
)
_MONEY_COUNT_FIELDS: tuple[Literal["sale_count", "refund_count"], ...] = (
    "sale_count",
    "refund_count",
)

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


def _statistics_defaults_to_metrics() -> Types.StatisticsMetricsValues:
    return {
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
        "stale": 0,
        "messages": 0,
        "conversations": 0,
        "transitions": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_credit": 0,
        "active_users": 0,
        "revenue": {},
    }


def _payment_defaults_to_bucket() -> _PaymentBucket:
    return {
        "sales": Decimal(0),
        "refunds": Decimal(0),
        "payment_ids": set(),
        "refund_count": 0,
    }


def payment_buckets_to_revenue(
    buckets: Mapping[str, _PaymentBucket],
) -> dict[str, Types.RevenueValues]:
    return {
        currency: {
            "sales": str(b["sales"]),
            "refunds": str(b["refunds"]),
            "net": str(b["sales"] - b["refunds"]),
            "sale_count": len(b["payment_ids"]),
            "refund_count": b["refund_count"],
        }
        for currency, b in buckets.items()
    }


def statistics_facts_infos_to_build_info(
    facts: Types.ReplaceStatisticsDayCommand,
) -> Types.StatisticsBuildInfo:
    metrics: defaultdict[UUID, Types.StatisticsMetricsValues] = defaultdict(
        _statistics_defaults_to_metrics
    )
    for snapshot_id, status, count, messages in facts.generations:
        metrics[snapshot_id][_STATUS_COUNTERS[status]] += count
        metrics[snapshot_id]["messages"] += messages or 0
    users = facts.users
    for snapshot_id, _user_id in users:
        metrics[snapshot_id]["active_users"] += 1
    for snapshot_id, input_tokens, output_tokens, cost_credit in facts.usage:
        metrics[snapshot_id]["input_tokens"] = input_tokens
        metrics[snapshot_id]["output_tokens"] = output_tokens
        metrics[snapshot_id]["cost_credit"] = cost_credit
    for snapshot_id, count in facts.conversations:
        metrics[snapshot_id]["conversations"] = count
    for snapshot_id, count in facts.transitions:
        metrics[snapshot_id]["transitions"] = count
    version_money: defaultdict[UUID, defaultdict[str, _PaymentBucket]] = defaultdict(
        lambda: defaultdict(_payment_defaults_to_bucket)
    )
    total_money: defaultdict[str, _PaymentBucket] = defaultdict(
        _payment_defaults_to_bucket
    )
    for snapshot_id, currency, kind, amount, count, payment_ids in facts.payments:
        for bucket in (version_money[snapshot_id][currency], total_money[currency]):
            if kind == "sale":
                bucket["sales"] += amount
                bucket["payment_ids"].update(payment_ids)
            else:
                bucket["refunds"] += amount
                bucket["refund_count"] += count
        metrics[snapshot_id]["revenue"] = payment_buckets_to_revenue(
            version_money[snapshot_id]
        )
    total = _statistics_defaults_to_metrics()
    for metric in metrics.values():
        for field in COUNTERS:
            total[field] += metric[field]
    unique_users = {user_id for _, user_id in users}
    total["active_users"] = len(unique_users)
    total["revenue"] = payment_buckets_to_revenue(total_money)
    return Types.StatisticsBuildInfo(dict(metrics), total, users, unique_users)


def statistics_report_row_to_info(
    report: StatisticsReportRow,
    product_id: UUID,
    snapshot_id: UUID | None,
    date_from: date,
    date_to: date,
) -> Types.StatisticsInfo:
    rows, active_users, pending = report
    total = _statistics_defaults_to_metrics()
    money: defaultdict[str, _PeriodRevenueBucket] = defaultdict(
        lambda: {
            "sales": Decimal(0),
            "refunds": Decimal(0),
            "net": Decimal(0),
            "sale_count": 0,
            "refund_count": 0,
        }
    )
    for row in rows:
        total["succeeded"] += row.succeeded
        total["failed"] += row.failed
        total["cancelled"] += row.cancelled
        total["stale"] += row.stale
        total["messages"] += row.messages
        total["conversations"] += row.conversations
        total["transitions"] += row.transitions
        total["input_tokens"] += row.input_tokens
        total["output_tokens"] += row.output_tokens
        total["cost_credit"] += row.cost_credit
        for currency, bucket in row.revenue.items():
            for money_field in _MONEY_FIELDS:
                money[currency][money_field] += Decimal(bucket[money_field])
            for count_field in _MONEY_COUNT_FIELDS:
                money[currency][count_field] += bucket[count_field]
    total["revenue"] = {
        currency: {
            "sales": str(bucket["sales"]),
            "refunds": str(bucket["refunds"]),
            "net": str(bucket["net"]),
            "sale_count": bucket["sale_count"],
            "refund_count": bucket["refund_count"],
        }
        for currency, bucket in money.items()
    }
    total["active_users"] = active_users
    return Types.StatisticsInfo(
        product_id=product_id,
        snapshot_id=snapshot_id,
        timezone="Asia/Seoul",
        date_from=date_from,
        date_to=date_to,
        totals=statistics_values_to_metrics_info(total),
        pending_days=pending,
        days=[statistics_row_to_day_info(row) for row in rows],
    )
