"""Pure conversion of credit-owned rows into immutable public values."""

from app.db.models.credit import CreditReservation
from app.modules.commerce.credit import repository as Repository
from app.modules.commerce.credit import types as Types


def credit_account_entity_to_info(
    row: Repository.CreditWalletRow,
) -> Types.CreditBalanceInfo | None:
    if row.wallet is None:
        return None
    buckets = {
        entity.bucket: Types.CreditBucketInfo(
            balance_credit=entity.balance,
            reserved_credit=entity.reserved_credit,
            available_credit=entity.balance - entity.reserved_credit,
        )
        for entity in row.balances
    }
    if set(buckets) != {"free", "paid"}:
        # Preserve malformed persisted structure as an error; never invent balances.
        raise ValueError("Incomplete credit wallet.")
    free, paid = buckets["free"], buckets["paid"]
    return Types.CreditBalanceInfo(
        user_id=row.wallet.user_id,
        currency_code=row.wallet.currency_code,
        balance_credit=free.balance_credit + paid.balance_credit,
        reserved_credit=free.reserved_credit + paid.reserved_credit,
        available_credit=free.available_credit + paid.available_credit,
        free=free,
        paid=paid,
    )


def credit_reservation_entity_to_info(
    entity: CreditReservation | None,
) -> Types.CreditReservationInfo | None:
    if entity is None:
        return None
    return Types.CreditReservationInfo(
        id=entity.id,
        currency_code=entity.currency_code,
        free_amount=entity.free_amount,
        paid_amount=entity.paid_amount,
        allocation_status=entity.allocation_status,
        user_id=entity.user_id,
        request_key=entity.request_key,
        namespace=entity.namespace,
        reference_id=entity.reference_id,
        reason=entity.reason,
        settlement_key=entity.settlement_key,
        transaction_id=entity.transaction_id,
        created_at=entity.created_at,
        finalized_at=entity.finalized_at,
        status=Types.CreditReservationStatus(entity.status),
        reserved_credit=entity.reserved_credit,
        result_id=entity.result_id,
    )


def credit_transaction_row_to_info(
    row: Repository.CreditTransactionRow | None,
) -> Types.CreditTransactionInfo | None:
    if row is None:
        return None
    entity = row.transaction
    amounts = {entry.bucket: entry.amount for entry in row.entries}
    return Types.CreditTransactionInfo(
        id=entity.id,
        user_id=entity.user_id,
        currency_code=entity.currency_code,
        namespace=entity.namespace,
        request_key=entity.request_key,
        operation=entity.operation,
        amount=entity.amount,
        reason=entity.reason,
        reference_id=entity.reference_id,
        idempotency_key=entity.idempotency_key,
        created_at=entity.created_at,
        free_amount=None if entity.operation == "legacy" else amounts.get("free", 0),
        paid_amount=None if entity.operation == "legacy" else amounts.get("paid", 0),
    )
