from typing import overload

from app.db.models.billing import Payment
from app.db.models.product_usage import ProductPaymentEvent
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
        **{
            key: getattr(entity, key)
            for key in Types.PaymentEventInfo.__dataclass_fields__
        }
    )


def billing_statistics_rows_to_info(rows) -> Types.BillingStatisticsInfo:
    return Types.BillingStatisticsInfo(
        *[[tuple(row) for row in group] for group in rows]
    )


def usage_entity_to_info(entity) -> Types.UsageRecordedInfo:
    return Types.UsageRecordedInfo(entity.id)
