# 결제 배분은 Payment, 환불은 원매출 이벤트 행의 FOR UPDATE 잠금 아래 누계를 조회한다.
# 통계는 [start, end) 범위의 버전별 집계다.
# 사용량은 created_at, 결제는 attributed_at 기준이다.
# 결제 금액은 통화별로 나누고 스냅샷 없는 사용량은 제외한다.
from dataclasses import asdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.billing import Payment, UsageLog
from app.db.models.billing_credit import BillingCreditBinding
from app.db.models.billing_quote import BillingQuote
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


async def get_billing_quote_by_key(
    session: AsyncSession, user_id: UUID, request_key: UUID
) -> BillingQuote | None:
    return await session.scalar(
        select(BillingQuote).where(
            BillingQuote.user_id == user_id,
            BillingQuote.request_key == request_key,
        )
    )


async def get_billing_quote(
    session: AsyncSession, user_id: UUID, quote_id: UUID
) -> BillingQuote | None:
    return await session.scalar(
        select(BillingQuote).where(
            BillingQuote.user_id == user_id,
            BillingQuote.id == quote_id,
        )
    )


async def create_billing_quote(
    session: AsyncSession,
    *,
    quote_id: UUID,
    user_id: UUID,
    request_key: UUID,
    request_snapshot: dict[str, Any],
    price_snapshot: dict[str, Any],
    created_at: datetime,
    expires_at: datetime,
) -> BillingQuote:
    entity = BillingQuote(
        id=quote_id,
        user_id=user_id,
        request_key=request_key,
        request_snapshot=request_snapshot,
        price_snapshot=price_snapshot,
        created_at=created_at,
        expires_at=expires_at,
    )
    session.add(entity)
    await session.flush()
    return entity


async def get_credit_binding(
    session: AsyncSession, user_id: UUID, request_key: UUID
) -> BillingCreditBinding | None:
    return await session.scalar(
        select(BillingCreditBinding)
        .where(
            BillingCreditBinding.user_id == user_id,
            BillingCreditBinding.request_key == request_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def get_credit_binding_by_quote(
    session: AsyncSession, quote_id: UUID
) -> BillingCreditBinding | None:
    return await session.scalar(
        select(BillingCreditBinding).where(BillingCreditBinding.quote_id == quote_id)
    )


async def create_credit_binding(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    quote_id: UUID,
    user_id: UUID,
    request_key: UUID,
    created_at: datetime,
) -> BillingCreditBinding:
    entity = BillingCreditBinding(
        reservation_id=reservation_id,
        quote_id=quote_id,
        user_id=user_id,
        request_key=request_key,
        created_at=created_at,
    )
    session.add(entity)
    await session.flush()
    return entity
