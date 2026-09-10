from dataclasses import asdict

from sqlalchemy import func, select

from app.db.models.billing import Payment, UsageLog
from app.db.models.product_usage import ProductPaymentEvent


async def create_usage_log(session, command) -> UsageLog:
    entity = UsageLog(**asdict(command))
    session.add(entity)
    await session.flush()
    return entity


async def get_payment_event_by_key(session, event_key):
    return await session.scalar(
        select(ProductPaymentEvent).where(ProductPaymentEvent.event_key == event_key)
    )


async def get_payment(session, payment_id):
    return await session.get(Payment, payment_id, with_for_update=True)


async def get_payment_event(session, sale_id):
    return await session.get(ProductPaymentEvent, sale_id, with_for_update=True)


async def get_first_payment_allocation(session, payment_id):
    return await session.scalar(
        select(ProductPaymentEvent.occurred_at)
        .where(
            ProductPaymentEvent.payment_id == payment_id,
            ProductPaymentEvent.kind == "sale",
        )
        .limit(1)
    )


async def sum_payment_allocations(session, payment_id):
    return await session.scalar(
        select(func.coalesce(func.sum(ProductPaymentEvent.amount), 0)).where(
            ProductPaymentEvent.payment_id == payment_id,
            ProductPaymentEvent.kind == "sale",
        )
    )


async def sum_sale_refunds(session, sale_id):
    return await session.scalar(
        select(func.coalesce(func.sum(ProductPaymentEvent.amount), 0)).where(
            ProductPaymentEvent.sale_id == sale_id
        )
    )


async def create_payment_event(session, **fields):
    row = ProductPaymentEvent(**fields)
    session.add(row)
    await session.flush()
    return row


async def get_statistics_facts(session, product_id, start, end):
    u = UsageLog
    usage = list(
        await session.execute(
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
    )
    e = ProductPaymentEvent
    payments = list(
        await session.execute(
            select(
                e.product_snapshot_id,
                e.currency,
                e.kind,
                func.sum(e.amount),
                func.count(),
                func.array_agg(func.distinct(e.payment_id)),
            )
            .where(
                e.product_id == product_id,
                e.attributed_at >= start,
                e.attributed_at < end,
            )
            .group_by(e.product_snapshot_id, e.currency, e.kind)
        )
    )
    return usage, payments
