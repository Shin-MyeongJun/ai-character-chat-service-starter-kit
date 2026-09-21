# 호출자가 검증한 확정 결제·환불을 상품 버전별 매출에 귀속하는 내부 인터페이스다.
# 키 잠금 후 동일 요청은 저장된 결과를 반환한다.
# 다른 내용의 키 재사용은 ValueError로 거절한다.
# 결제/원매출 행을 잠가 배분·환불 누계를 검사한다.
# 같은 트랜잭션에서 통계 재집계를 요청한다.
"""Internal billing interface; caller must supply a verified settled payment/refund.

This records attribution only. It neither charges a customer nor changes balances.
"""

from datetime import UTC, datetime
from decimal import Decimal

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import persistence as PersistenceMapper
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)


def _validate_payment_event(event_key, amount, occurred_at):
    if not event_key.strip() or len(event_key) > 200:
        raise ValueError("Invalid billing event key.")
    if (
        not isinstance(amount, Decimal)
        or not amount.is_finite()
        or (not 0 < amount < Decimal(100000000))
        or (amount != amount.quantize(Decimal(".01")))
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


# 확정 Payment의 미배분 금액 안에서 상품 버전에 매출을 귀속한다.
# 같은 결제의 배분은 정산 시각을 공유한다.
async def record_sale(
    session, command: Types.RecordSaleCommand
) -> Types.PaymentEventInfo:
    payment_id = command.payment_id
    snapshot_id = command.snapshot_id
    event_key = command.event_key
    amount = command.amount
    occurred_at = command.occurred_at
    _validate_payment_event(event_key, amount, occurred_at)
    async with use_case_transaction(session):
        await lock_key(session, "payment-event", event_key)
        row = await Repository.get_payment_event_by_key(session, event_key)
        existing = PersistenceMapper.payment_event_entity_to_info(row)
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
            return existing
        row = await Repository.get_payment(session, payment_id)
        payment = PersistenceMapper.payment_entity_to_info(row)
        if payment is None or payment.status not in ("succeeded", "refunded"):
            raise ValueError("A settled payment is required.")
        first_allocation = await Repository.get_first_payment_allocation(
            session, payment_id
        )
        if first_allocation is not None and first_allocation != occurred_at:
            raise ValueError(
                "Allocations of one payment must share its settlement timestamp."
            )
        snapshot = await ProductQueryService.get_product_snapshot(
            session, ProductTypes.ProductSnapshotCommand(snapshot_id)
        )
        if snapshot is None or snapshot.product_id is None:
            raise LookupError("Product version not found.")
        allocated = await Repository.sum_payment_allocations(session, payment_id)
        if allocated + amount > payment.amount:
            raise ValueError("Allocation exceeds the original payment amount.")
        row = await Repository.create_payment_event(
            session,
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
        info = PersistenceMapper.payment_event_entity_to_info(row)
        await mark_statistics_dirty(
            session,
            ProductTypes.MarkStatisticsDirtyCommand(
                info.product_id, info.attributed_at
            ),
        )
        return info


# 원매출을 잠그고 누적 환불 한도를 확인한다.
# 환불 발생일과 달라도 통계는 원매출 귀속일을 갱신한다.
async def record_refund(
    session, command: Types.RecordRefundCommand
) -> Types.PaymentEventInfo:
    sale_id = command.sale_id
    event_key = command.event_key
    amount = command.amount
    occurred_at = command.occurred_at
    _validate_payment_event(event_key, amount, occurred_at)
    async with use_case_transaction(session):
        await lock_key(session, "payment-event", event_key)
        row = await Repository.get_payment_event_by_key(session, event_key)
        existing = PersistenceMapper.payment_event_entity_to_info(row)
        if existing:
            if (
                existing.kind,
                existing.sale_id,
                existing.amount,
                existing.occurred_at,
            ) != ("refund", sale_id, amount, occurred_at):
                raise ValueError("Billing event key conflicts with existing refund.")
            return existing
        row = await Repository.get_payment_event(session, sale_id)
        sale = PersistenceMapper.payment_event_entity_to_info(row)
        if sale is None or sale.kind != "sale":
            raise LookupError("Original sale not found.")
        if occurred_at < sale.occurred_at:
            raise ValueError("Refund cannot precede its original sale.")
        refunded = await Repository.sum_sale_refunds(session, sale.id)
        if refunded + amount > sale.amount:
            raise ValueError("Refund exceeds the attributed sale amount.")
        row = await Repository.create_payment_event(
            session,
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
        info = PersistenceMapper.payment_event_entity_to_info(row)
        await mark_statistics_dirty(
            session,
            ProductTypes.MarkStatisticsDirtyCommand(
                info.product_id, info.attributed_at
            ),
        )
        return info
