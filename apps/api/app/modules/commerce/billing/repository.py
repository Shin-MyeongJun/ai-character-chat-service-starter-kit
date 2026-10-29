# 결제 배분은 Payment, 환불은 원매출 이벤트 행의 FOR UPDATE 잠금 아래 누계를 조회한다.
# 통계는 [start, end) 범위의 버전별 집계다.
# 사용량은 created_at, 결제는 attributed_at 기준이다.
# 결제 금액은 통화별로 나누고 스냅샷 없는 사용량은 제외한다.
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Literal, TypeAlias, TypedDict
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.billing import Payment, UsageLog
from app.db.models.billing_credit import BillingCreditBinding
from app.db.models.billing_quote import BillingQuote
from app.db.models.product_usage import ProductPaymentEvent
from app.modules.commerce.billing import types as Types

UsageStatisticsRow: TypeAlias = tuple[UUID | None, int, int, int | Decimal]
PaymentStatisticsRow: TypeAlias = tuple[UUID, str, str, Decimal, int, Sequence[UUID]]
BillingStatisticsRows: TypeAlias = tuple[
    list[UsageStatisticsRow], list[PaymentStatisticsRow]
]
AccountUsageStatisticsRow: TypeAlias = tuple[int, int, int, int | Decimal]


class BillingQuoteSnapshot(TypedDict):
    """Version 1 JSON envelope; the mapper serializes its request/price value."""

    schema_version: Literal[1]
    value: dict[str, object]


async def create_usage_log(
    session: AsyncSession, command: Types.RecordUsageCommand
) -> UsageLog:
    entity = UsageLog(**asdict(command))
    session.add(entity)
    await session.flush()
    return entity


async def get_payment_event_by_key(
    session: AsyncSession, event_key: str
) -> ProductPaymentEvent | None:
    result = await session.scalars(
        select(ProductPaymentEvent).where(ProductPaymentEvent.event_key == event_key)
    )
    return result.first()


async def get_payment(session: AsyncSession, payment_id: UUID) -> Payment | None:
    return await session.get(Payment, payment_id, with_for_update=True)


async def get_payment_event(
    session: AsyncSession, sale_id: UUID
) -> ProductPaymentEvent | None:
    return await session.get(ProductPaymentEvent, sale_id, with_for_update=True)


async def get_first_payment_allocation(
    session: AsyncSession, payment_id: UUID
) -> datetime | None:
    result = await session.scalars(
        select(ProductPaymentEvent.occurred_at)
        .where(
            ProductPaymentEvent.payment_id == payment_id,
            ProductPaymentEvent.kind == "sale",
        )
        .limit(1)
    )
    return result.first()


async def sum_payment_allocations(session: AsyncSession, payment_id: UUID) -> Decimal:
    # Numeric amount plus COALESCE guarantees one non-null Decimal aggregate.
    statement: Select[tuple[Decimal]] = select(
        func.coalesce(func.sum(ProductPaymentEvent.amount), 0)
    ).where(
        ProductPaymentEvent.payment_id == payment_id,
        ProductPaymentEvent.kind == "sale",
    )
    return (await session.execute(statement)).scalar_one()


async def sum_sale_refunds(session: AsyncSession, sale_id: UUID) -> Decimal:
    statement: Select[tuple[Decimal]] = select(
        func.coalesce(func.sum(ProductPaymentEvent.amount), 0)
    ).where(ProductPaymentEvent.sale_id == sale_id)
    return (await session.execute(statement)).scalar_one()


async def create_payment_event(
    session: AsyncSession,
    *,
    payment_id: UUID,
    product_id: UUID,
    product_snapshot_id: UUID,
    event_key: str,
    kind: str,
    amount: Decimal,
    currency: str,
    occurred_at: datetime,
    attributed_at: datetime,
    sale_id: UUID | None = None,
) -> ProductPaymentEvent:
    entity = ProductPaymentEvent(
        payment_id=payment_id,
        product_id=product_id,
        product_snapshot_id=product_snapshot_id,
        event_key=event_key,
        kind=kind,
        amount=amount,
        currency=currency,
        occurred_at=occurred_at,
        attributed_at=attributed_at,
        sale_id=sale_id,
    )
    session.add(entity)
    await session.flush()
    return entity


async def get_statistics_facts(
    session: AsyncSession, product_id: UUID, start: datetime, end: datetime
) -> BillingStatisticsRows:
    u = UsageLog
    usage: list[UsageStatisticsRow] = list(
        (
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
        ).tuples()
    )
    e = ProductPaymentEvent
    # SQL DISTINCT preserves the non-null UUID type of payment_id.
    distinct_payment_id: ColumnElement[UUID] = func.distinct(e.payment_id)
    payments: list[PaymentStatisticsRow] = list(
        (
            await session.execute(
                select(
                    e.product_snapshot_id,
                    e.currency,
                    e.kind,
                    func.sum(e.amount),
                    func.count(),
                    func.array_agg(distinct_payment_id),
                )
                .where(
                    e.product_id == product_id,
                    e.attributed_at >= start,
                    e.attributed_at < end,
                )
                .group_by(e.product_snapshot_id, e.currency, e.kind)
            )
        ).tuples()
    )
    return usage, payments


async def get_billing_quote_by_key(
    session: AsyncSession, user_id: UUID, request_key: UUID
) -> BillingQuote | None:
    result = await session.scalars(
        select(BillingQuote).where(
            BillingQuote.user_id == user_id,
            BillingQuote.request_key == request_key,
        )
    )
    return result.first()


async def get_billing_quote(
    session: AsyncSession, user_id: UUID, quote_id: UUID
) -> BillingQuote | None:
    result = await session.scalars(
        select(BillingQuote).where(
            BillingQuote.user_id == user_id,
            BillingQuote.id == quote_id,
        )
    )
    return result.first()


async def create_billing_quote(
    session: AsyncSession,
    *,
    quote_id: UUID,
    user_id: UUID,
    request_key: UUID,
    request_snapshot: BillingQuoteSnapshot,
    price_snapshot: BillingQuoteSnapshot,
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
    result = await session.scalars(
        select(BillingCreditBinding)
        .where(
            BillingCreditBinding.user_id == user_id,
            BillingCreditBinding.request_key == request_key,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.first()


async def get_credit_binding_by_quote(
    session: AsyncSession, quote_id: UUID
) -> BillingCreditBinding | None:
    result = await session.scalars(
        select(BillingCreditBinding).where(BillingCreditBinding.quote_id == quote_id)
    )
    return result.first()


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


async def get_account_usage_statistics(
    session: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> AccountUsageStatisticsRow:
    """사용자 스코프의 저장된 usage만 생성 시각 [start,end)로 합산한다."""
    u = UsageLog
    return (
        (
            await session.execute(
                select(
                    func.count(u.id),
                    func.coalesce(func.sum(u.input_tokens), 0),
                    func.coalesce(func.sum(u.output_tokens), 0),
                    func.coalesce(func.sum(u.cost_credit), 0),
                ).where(u.user_id == user_id, u.created_at >= start, u.created_at < end)
            )
        )
        .tuples()
        .one()
    )
