# 생성/대화/버전전환/usage/결제 사실을 통화별 Decimal 집계로 합친다. 환율 변환은 하지 않는다.
# 매출은 문자열로 반환하고 활성 사용자는 성공 생성 사용자의 중복을 제거한다.
from collections import defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.content.product import types as Types
from app.modules.content.product.mapper.persistence import (
    statistics_row_to_day_info,
    statistics_values_to_metrics_info,
)

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


def _statistics_defaults_to_metrics() -> dict[str, Any]:
    return {**dict.fromkeys(COUNTERS, 0), "active_users": 0, "revenue": {}}


def _payment_defaults_to_bucket() -> dict[str, Any]:
    return {
        "sales": Decimal(0),
        "refunds": Decimal(0),
        "payment_ids": set(),
        "refund_count": 0,
    }


def payment_buckets_to_revenue(buckets):
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


def statistics_facts_infos_to_build_info(facts) -> Types.StatisticsBuildInfo:
    metrics: dict[UUID, dict[str, Any]] = defaultdict(_statistics_defaults_to_metrics)
    rows = facts.generations
    for sid, status, count, messages in rows:
        metrics[sid][status] += count
        metrics[sid]["messages"] += messages or 0
    users = facts.users
    for sid, _uid in users:
        metrics[sid]["active_users"] += 1
    rows = facts.usage
    for sid, input_tokens, output_tokens, cost_credit in rows:
        metrics[sid].update(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_credit=cost_credit,
        )
    rows = facts.conversations
    for sid, count in rows:
        metrics[sid]["conversations"] = count
    rows = facts.transitions
    for sid, count in rows:
        metrics[sid]["transitions"] = count
    version_money: dict[UUID, dict[str, dict[str, Any]]] = defaultdict(
        lambda: defaultdict(_payment_defaults_to_bucket)
    )
    total_money: dict[str, dict[str, Any]] = defaultdict(_payment_defaults_to_bucket)
    rows = facts.payments
    for sid, currency, kind, amount, count, payment_ids in rows:
        for bucket in (version_money[sid][currency], total_money[currency]):
            if kind == "sale":
                bucket["sales"] += amount
                bucket["payment_ids"].update(payment_ids)
            else:
                bucket["refunds"] += amount
                bucket["refund_count"] += count
        metrics[sid]["revenue"] = payment_buckets_to_revenue(version_money[sid])
    total = _statistics_defaults_to_metrics()
    for metric in metrics.values():
        for field in COUNTERS:
            total[field] += metric[field]
    unique_users = {uid for _, uid in users}
    total["active_users"] = len(unique_users)
    total["revenue"] = payment_buckets_to_revenue(total_money)
    return Types.StatisticsBuildInfo(dict(metrics), total, users, unique_users)


def statistics_report_row_to_info(
    report, product_id, snapshot_id, date_from, date_to
) -> Types.StatisticsInfo:
    rows, active_users, pending = report
    total = _statistics_defaults_to_metrics()
    money: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "sales": Decimal(0),
            "refunds": Decimal(0),
            "net": Decimal(0),
            "sale_count": 0,
            "refund_count": 0,
        }
    )
    for row in rows:
        for field in COUNTERS:
            total[field] += getattr(row, field)
        for currency, bucket in row.revenue.items():
            for field in ("sales", "refunds", "net"):
                money[currency][field] += Decimal(bucket[field])
            for field in ("sale_count", "refund_count"):
                money[currency][field] += bucket[field]
    total["revenue"] = {
        currency: {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in bucket.items()
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
