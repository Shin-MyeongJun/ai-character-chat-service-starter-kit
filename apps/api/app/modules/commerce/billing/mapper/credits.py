"""Pure conversion of billing-owned balance and reservation entities."""

from app.db.models.billing import CreditAccount
from app.db.models.billing_credit import CreditReservation
from app.modules.commerce.billing import types as Types


def credit_account_entity_to_info(
    entity: CreditAccount | None,
) -> Types.CreditBalanceInfo | None:
    if entity is None:
        return None
    return Types.CreditBalanceInfo(
        user_id=entity.user_id,
        balance_credit=entity.balance,
        reserved_credit=entity.reserved_credit,
        available_credit=entity.balance - entity.reserved_credit,
    )


def credit_reservation_entity_to_info(
    entity: CreditReservation | None,
) -> Types.CreditReservationInfo | None:
    if entity is None:
        return None
    return Types.CreditReservationInfo(
        id=entity.id,
        user_id=entity.user_id,
        request_key=entity.request_key,
        quote_id=entity.quote_id,
        status=Types.CreditReservationStatus(entity.status),
        reserved_credit=entity.reserved_credit,
        result_id=entity.result_id,
    )
