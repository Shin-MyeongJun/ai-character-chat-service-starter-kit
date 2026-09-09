"""Rebuild affected days from facts, never increment cached totals blindly."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, insert, select

from app.db.models.billing import UsageLog
from app.db.models.chat import Conversation, ConversationVersionChange
from app.db.models.product import Product
from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)
from app.db.models.product_usage import ProductGeneration, ProductPaymentEvent
from app.db.models.snapshot.product import ProductSnapshot
from app.db.product_stats_queue import day_bounds, mark_dirty, statistics_day
from app.modules.content.product import repository

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


def empty_metrics():
    return {**dict.fromkeys(COUNTERS, 0), "active_users": 0, "revenue": {}}


def money_bucket():
    return {
        "sales": Decimal(0),
        "refunds": Decimal(0),
        "payment_ids": set(),
        "refund_count": 0,
    }


def serialize_money(buckets):
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


async def rebuild_day(session, *, product_id, day):
    """Caller holds the dirty-day row lock until this transaction commits."""
    start, end = day_bounds(day)
    metrics = defaultdict(empty_metrics)
    g = ProductGeneration
    rows = await session.execute(
        select(g.product_snapshot_id, g.status, func.count(), func.sum(g.message_count))
        .where(g.product_id == product_id, g.finished_at >= start, g.finished_at < end)
        .group_by(g.product_snapshot_id, g.status)
    )
    for sid, status, count, messages in rows:
        metrics[sid][status] += count
        metrics[sid]["messages"] += messages or 0
    users = list(
        await session.execute(
            select(g.product_snapshot_id, g.user_id)
            .where(
                g.product_id == product_id,
                g.status == "succeeded",
                g.finished_at >= start,
                g.finished_at < end,
            )
            .distinct()
        )
    )
    for sid, _uid in users:
        metrics[sid]["active_users"] += 1
    u = UsageLog
    rows = await session.execute(
        select(
            u.product_snapshot_id,
            func.sum(u.input_tokens),
            func.sum(u.output_tokens),
            func.sum(u.cost_credit),
        )
        .where(
            u.product_id == product_id,
            u.product_snapshot_id.is_not(None),
            u.created_at >= start,
            u.created_at < end,
        )
        .group_by(u.product_snapshot_id)
    )
    for sid, input_tokens, output_tokens, cost_credit in rows:
        metrics[sid].update(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_credit=cost_credit,
        )
    rows = await session.execute(
        select(Conversation.initial_snapshot_id, func.count())
        .where(
            Conversation.product_id == product_id,
            Conversation.initial_snapshot_id.is_not(None),
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
        .group_by(Conversation.initial_snapshot_id)
    )
    for sid, count in rows:
        metrics[sid]["conversations"] = count
    change = ConversationVersionChange
    rows = await session.execute(
        select(change.to_snapshot_id, func.count())
        .join(Conversation, Conversation.id == change.conversation_id)
        .where(
            Conversation.product_id == product_id,
            change.created_at >= start,
            change.created_at < end,
        )
        .group_by(change.to_snapshot_id)
    )
    for sid, count in rows:
        metrics[sid]["transitions"] = count
    event = ProductPaymentEvent
    version_money = defaultdict(lambda: defaultdict(money_bucket))
    total_money = defaultdict(money_bucket)
    rows = await session.execute(
        select(
            event.product_snapshot_id,
            event.currency,
            event.kind,
            func.sum(event.amount),
            func.count(),
            func.array_agg(func.distinct(event.payment_id)),
        )
        .where(
            event.product_id == product_id,
            event.attributed_at >= start,
            event.attributed_at < end,
        )
        .group_by(event.product_snapshot_id, event.currency, event.kind)
    )
    for sid, currency, kind, amount, count, payment_ids in rows:
        for bucket in (version_money[sid][currency], total_money[currency]):
            if kind == "sale":
                bucket["sales"] += amount
                bucket["payment_ids"].update(payment_ids)
            else:
                bucket["refunds"] += amount
                bucket["refund_count"] += count
        metrics[sid]["revenue"] = serialize_money(version_money[sid])
    total = empty_metrics()
    for metric in metrics.values():
        for field in COUNTERS:
            total[field] += metric[field]
    unique_users = {uid for _, uid in users}
    total["active_users"] = len(unique_users)
    total["revenue"] = serialize_money(total_money)
    for cls in (
        ProductDailyStats,
        ProductVersionDailyStats,
        ProductUserDailyActivity,
        ProductVersionUserDailyActivity,
    ):
        await session.execute(
            delete(cls).where(cls.product_id == product_id, cls.day == day)
        )
    now = datetime.now(UTC)
    session.add(
        ProductDailyStats(product_id=product_id, day=day, updated_at=now, **total)
    )
    session.add_all(
        ProductVersionDailyStats(
            product_id=product_id,
            product_snapshot_id=sid,
            day=day,
            updated_at=now,
            **metric,
        )
        for sid, metric in metrics.items()
    )
    if users:
        await session.execute(
            insert(ProductVersionUserDailyActivity),
            [
                {
                    "product_id": product_id,
                    "product_snapshot_id": sid,
                    "day": day,
                    "user_id": uid,
                }
                for sid, uid in users
            ],
        )
        await session.execute(
            insert(ProductUserDailyActivity),
            [
                {"product_id": product_id, "day": day, "user_id": uid}
                for uid in unique_users
            ],
        )
    await session.flush()


async def process_pending(session, *, limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError("Batch limit must be 1–1000.")
    processed = 0
    for _ in range(limit):
        async with session.begin():
            work = await session.scalar(
                select(ProductStatsDirtyDay)
                .order_by(
                    ProductStatsDirtyDay.requested_at,
                    ProductStatsDirtyDay.product_id,
                    ProductStatsDirtyDay.day,
                )
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if work is None:
                break
            await rebuild_day(session, product_id=work.product_id, day=work.day)
            await session.delete(work)
        processed += 1
    return processed


async def enqueue_recent(session, *, days=7, now=None):
    """Nightly repair alongside the normal event-driven dirty queue."""
    if not 1 <= days <= 31:
        raise ValueError("Repair range must be 1–31 days.")
    today = statistics_day(now or datetime.now(UTC))
    async with session.begin():
        product_ids = list(
            await session.scalars(
                select(Product.id).where(Product.latest_snapshot_id.is_not(None))
            )
        )
        for pid in product_ids:
            for offset in range(days + 1):
                start, _ = day_bounds(today - timedelta(days=offset))
                await mark_dirty(session, pid, start)


async def get_statistics(
    session, *, product_id, owner_id, date_from, date_to, snapshot_id=None
):
    if date_to < date_from or (date_to - date_from).days > 730:
        raise ValueError("Statistics range must be ordered and at most 731 days.")
    await repository.owned(session, product_id, owner_id)
    if snapshot_id is not None:
        snapshot = await session.scalar(
            select(ProductSnapshot.id).where(
                ProductSnapshot.id == snapshot_id,
                ProductSnapshot.product_id == product_id,
            )
        )
        if snapshot is None:
            raise LookupError("Version not found.")
    cls = ProductVersionDailyStats if snapshot_id else ProductDailyStats
    activity = (
        ProductVersionUserDailyActivity if snapshot_id else ProductUserDailyActivity
    )
    filters = [cls.product_id == product_id, cls.day >= date_from, cls.day <= date_to]
    activity_filters = [
        activity.product_id == product_id,
        activity.day >= date_from,
        activity.day <= date_to,
    ]
    if snapshot_id:
        filters.append(cls.product_snapshot_id == snapshot_id)
        activity_filters.append(activity.product_snapshot_id == snapshot_id)
    rows = list(await session.scalars(select(cls).where(*filters).order_by(cls.day)))
    total = empty_metrics()
    money = defaultdict(
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
    total["active_users"] = await session.scalar(
        select(func.count(func.distinct(activity.user_id))).where(*activity_filters)
    )
    pending = list(
        await session.scalars(
            select(ProductStatsDirtyDay.day)
            .where(
                ProductStatsDirtyDay.product_id == product_id,
                ProductStatsDirtyDay.day >= date_from,
                ProductStatsDirtyDay.day <= date_to,
            )
            .order_by(ProductStatsDirtyDay.day)
        )
    )
    return {
        "product_id": product_id,
        "snapshot_id": snapshot_id,
        "timezone": "Asia/Seoul",
        "date_from": date_from,
        "date_to": date_to,
        "totals": total,
        "pending_days": pending,
        "days": [
            {
                "day": r.day,
                "updated_at": r.updated_at,
                **{field: getattr(r, field) for field in COUNTERS},
                "active_users": r.active_users,
                "revenue": r.revenue,
            }
            for r in rows
        ],
    }
