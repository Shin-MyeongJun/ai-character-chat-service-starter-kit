"""Billing binding persistence and public credit-to-billing value conversion."""

from app.db.models.billing_credit import BillingCreditBinding
from app.modules.commerce.billing import types as Types
from app.modules.commerce.credit import types as CreditTypes


def credit_binding_entity_to_info(
    entity: BillingCreditBinding | None,
) -> Types.CreditBindingInfo | None:
    if entity is None:
        return None
    return Types.CreditBindingInfo(
        reservation_id=entity.reservation_id,
        quote_id=entity.quote_id,
        user_id=entity.user_id,
        request_key=entity.request_key,
        created_at=entity.created_at,
    )


def credit_balance_info_to_info(
    info: CreditTypes.CreditBalanceInfo,
) -> Types.CreditBalanceInfo:
    return Types.CreditBalanceInfo(
        user_id=info.user_id,
        balance_credit=info.balance_credit,
        reserved_credit=info.reserved_credit,
        available_credit=info.available_credit,
    )


def credit_reservation_binding_infos_to_info(
    info: CreditTypes.CreditReservationInfo,
    binding: Types.CreditBindingInfo,
) -> Types.CreditReservationInfo:
    return Types.CreditReservationInfo(
        id=info.id,
        user_id=info.user_id,
        request_key=info.request_key,
        quote_id=binding.quote_id,
        status=Types.CreditReservationStatus(info.status),
        reserved_credit=info.reserved_credit,
        result_id=info.result_id,
    )
