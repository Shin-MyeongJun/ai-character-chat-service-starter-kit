# DB 결제·귀속·사용량 행을 공개 Info로 변환한다.
# 집계 튜플 순서는 repository SELECT 순서를 따른다.
from typing import cast, overload
from uuid import UUID

from app.db.models.billing import Payment, UsageLog
from app.db.models.product_usage import ProductPaymentEvent
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types


@overload
def payment_entity_to_info(entity: Payment) -> Types.PaymentInfo: ...


@overload
def payment_entity_to_info(entity: None) -> None: ...


def payment_entity_to_info(entity: Payment | None) -> Types.PaymentInfo | None:
    if entity is None:
        return None
    return Types.PaymentInfo(entity.id, entity.status, entity.amount, entity.currency)


@overload
def payment_event_entity_to_info(
    entity: ProductPaymentEvent,
) -> Types.PaymentEventInfo: ...


@overload
def payment_event_entity_to_info(entity: None) -> None: ...


def payment_event_entity_to_info(
    entity: ProductPaymentEvent | None,
) -> Types.PaymentEventInfo | None:
    if entity is None:
        return None
    return Types.PaymentEventInfo(
        id=entity.id,
        payment_id=entity.payment_id,
        product_id=entity.product_id,
        product_snapshot_id=entity.product_snapshot_id,
        sale_id=entity.sale_id,
        kind=entity.kind,
        amount=entity.amount,
        currency=entity.currency,
        occurred_at=entity.occurred_at,
        attributed_at=entity.attributed_at,
    )


def billing_statistics_rows_to_info(
    rows: Repository.BillingStatisticsRows,
) -> Types.BillingStatisticsInfo:
    usage_rows, payment_rows = rows
    return Types.BillingStatisticsInfo(
        usage=[
            # get_statistics_facts excludes NULL snapshot IDs in its WHERE clause.
            # SUM(bigint) may be Decimal, but a sum of credit counts is integral.
            (cast(UUID, snapshot_id), input_tokens, output_tokens, int(cost_credit))
            for snapshot_id, input_tokens, output_tokens, cost_credit in usage_rows
        ],
        payments=[
            # PostgreSQL/asyncpg ARRAY(UUID) returns a list, not an arbitrary Sequence.
            (snapshot_id, currency, kind, amount, count, cast(list[UUID], payment_ids))
            for snapshot_id, currency, kind, amount, count, payment_ids in payment_rows
        ],
    )


def usage_entity_to_info(entity: UsageLog) -> Types.UsageRecordedInfo:
    return Types.UsageRecordedInfo(entity.id)


def account_usage_statistics_row_to_info(
    row: Repository.AccountUsageStatisticsRow,
) -> Types.AccountUsageStatisticsInfo:
    """저장된 사용량 합계와 행 수를 변환한다. 잔액·환불·공급자 비용은 계산하지 않는다."""
    return Types.AccountUsageStatisticsInfo(*(int(value) for value in row))
