"""Internal billing interface; caller must supply a verified settled payment/refund.

This records attribution only. It neither charges a customer nor changes balances.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.db.idempotency import lock_key
from app.db.models.billing import Payment
from app.db.models.product_usage import ProductPaymentEvent
from app.db.models.snapshot.product import ProductSnapshot
from app.db.product_stats_queue import mark_dirty


def validate(event_key, amount, occurred_at):
    if not event_key.strip() or len(event_key) > 200:
        raise ValueError("Invalid billing event key.")
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or not 0 < amount < Decimal(100000000)
        or amount != amount.quantize(Decimal(".01"))
    ):
        raise ValueError(
            "Amount must be a positive decimal with at most two fractional digits."
        )
    if (
        occurred_at.tzinfo is None
        or occurred_at.utcoffset() is None
        or occurred_at > datetime.now(UTC)
    ):
        raise ValueError("Event time must be timezone-aware and not in the future.")


async def record_sale(
    session, *, payment_id, snapshot_id, event_key, amount, occurred_at
):
    validate(event_key, amount, occurred_at)
    async with session.begin():
        await lock_key(session, "payment-event", event_key)
        existing = await session.scalar(
            select(ProductPaymentEvent).where(
                ProductPaymentEvent.event_key == event_key
            )
        )
        if existing:
            if (
                existing.kind,
                existing.payment_id,
                existing.product_snapshot_id,
                existing.amount,
                existing.occurred_at,
            ) != ("sale", payment_id, snapshot_id, amount, occurred_at):
                raise ValueError(
                    "Billing event key conflicts with existing attribution."
                )
            return existing.id
        payment = await session.get(Payment, payment_id, with_for_update=True)
        if payment is None or payment.status not in ("succeeded", "refunded"):
            raise ValueError("A settled payment is required.")
        first_allocation = await session.scalar(
            select(ProductPaymentEvent.occurred_at)
            .where(
                ProductPaymentEvent.payment_id == payment_id,
                ProductPaymentEvent.kind == "sale",
            )
            .limit(1)
        )
        if first_allocation is not None and first_allocation != occurred_at:
            raise ValueError(
                "Allocations of one payment must share its settlement timestamp."
            )
        snapshot = await session.get(ProductSnapshot, snapshot_id)
        if snapshot is None or snapshot.product_id is None:
            raise LookupError("Product version not found.")
        allocated = await session.scalar(
            select(func.coalesce(func.sum(ProductPaymentEvent.amount), 0)).where(
                ProductPaymentEvent.payment_id == payment_id,
                ProductPaymentEvent.kind == "sale",
            )
        )
        if allocated + amount > payment.amount:
            raise ValueError("Allocation exceeds the original payment amount.")
        row = ProductPaymentEvent(
            payment_id=payment_id,
            product_id=snapshot.product_id,
            product_snapshot_id=snapshot.id,
            event_key=event_key,
            kind="sale",
            amount=amount,
            currency=payment.currency,
            occurred_at=occurred_at,
            attributed_at=occurred_at,
        )
        session.add(row)
        await session.flush()
        await mark_dirty(session, row.product_id, row.attributed_at)
        return row.id


async def record_refund(session, *, sale_id, event_key, amount, occurred_at):
    validate(event_key, amount, occurred_at)
    async with session.begin():
        await lock_key(session, "payment-event", event_key)
        existing = await session.scalar(
            select(ProductPaymentEvent).where(
                ProductPaymentEvent.event_key == event_key
            )
        )
        if existing:
            if (
                existing.kind,
                existing.sale_id,
                existing.amount,
                existing.occurred_at,
            ) != ("refund", sale_id, amount, occurred_at):
                raise ValueError("Billing event key conflicts with existing refund.")
            return existing.id
        sale = await session.get(ProductPaymentEvent, sale_id, with_for_update=True)
        if sale is None or sale.kind != "sale":
            raise LookupError("Original sale not found.")
        if occurred_at < sale.occurred_at:
            raise ValueError("Refund cannot precede its original sale.")
        refunded = await session.scalar(
            select(func.coalesce(func.sum(ProductPaymentEvent.amount), 0)).where(
                ProductPaymentEvent.sale_id == sale.id
            )
        )
        if refunded + amount > sale.amount:
            raise ValueError("Refund exceeds the attributed sale amount.")
        row = ProductPaymentEvent(
            payment_id=sale.payment_id,
            sale_id=sale.id,
            product_id=sale.product_id,
            product_snapshot_id=sale.product_snapshot_id,
            event_key=event_key,
            kind="refund",
            amount=amount,
            currency=sale.currency,
            occurred_at=occurred_at,
            attributed_at=sale.attributed_at,
        )
        session.add(row)
        await session.flush()
        await mark_dirty(session, row.product_id, row.attributed_at)
        return row.id
