"""Server-only credit operations inside an explicit caller-owned transaction."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransactionOrigin

from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import credits as CreditPersistenceMapper
from app.modules.commerce.billing.service import quotes as QuoteService


def _get_utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_identifiers(*identifiers: UUID) -> None:
    if not all(isinstance(value, UUID) for value in identifiers):
        raise Types.CreditReservationConflictError("Credit identifiers must be UUIDs.")


def _require_credit_transaction(session: AsyncSession) -> None:
    transaction = session.sync_session.get_transaction()
    if transaction is None or transaction.origin is SessionTransactionOrigin.AUTOBEGIN:
        raise RuntimeError(
            "Credit writes require an explicit caller-owned transaction."
        )


async def _get_credit_balance(
    session: AsyncSession, user_id: UUID, *, for_update: bool
) -> Types.CreditBalanceInfo:
    row = await Repository.get_credit_account(session, user_id, for_update=for_update)
    info = CreditPersistenceMapper.credit_account_entity_to_info(row)
    if info is None:
        raise Types.CreditAccountNotFoundError("Credit account not found.")
    return info


async def get_credit_balance(
    session: AsyncSession, command: Types.GetCreditBalanceCommand
) -> Types.CreditBalanceInfo:
    """One statement reads held, reserved and available credit consistently."""
    _validate_identifiers(command.user_id)
    return await _get_credit_balance(session, command.user_id, for_update=False)


async def reserve_credit(
    session: AsyncSession,
    command: Types.ReserveCreditCommand,
    *,
    clock: Callable[[], datetime] = _get_utc_now,
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.quote_id)
    if (command.user_id, command.request_key) != (
        command.request.user_id,
        command.request.request_key,
    ):
        raise Types.CreditReservationConflictError(
            "Reservation and execution identity differ."
        )
    # Savepoint keeps this operation atomic even if the outer caller catches an error.
    # It never commits the caller's transaction; successful locks live until outer end.
    async with session.begin_nested():
        balance = await _get_credit_balance(session, command.user_id, for_update=True)
        now = QuoteService._get_quote_time(clock)
        row = await Repository.get_credit_reservation_by_key(
            session, command.user_id, command.request_key
        )
        existing = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
        if existing is not None and existing.quote_id != command.quote_id:
            raise Types.CreditReservationConflictError(
                "Request key already binds another quote."
            )
        query = Types.GetBillingQuoteCommand(
            quote_id=command.quote_id, request=command.request
        )
        quote = await QuoteService.get_billing_quote(session, query, clock=lambda: now)
        if existing is not None:
            # Match the full immutable request, but expiry cannot invalidate a retry.
            return existing
        row = await Repository.get_credit_reservation_by_quote(
            session, command.quote_id
        )
        used = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
        if used is not None:
            raise Types.CreditReservationConflictError("Quote has already been used.")
        if quote.status is Types.BillingQuoteStatus.EXPIRED:
            raise Types.BillingQuoteExpiredError(
                "Billing quote expired; obtain a new quote."
            )
        amount = quote.price.final_price_credit
        if balance.available_credit < amount:
            raise Types.InsufficientCreditError("Insufficient available credit.")
        await Repository.change_credit_balance(
            session, command.user_id, balance_delta=0, reserved_delta=amount
        )
        row = await Repository.create_credit_reservation(
            session,
            reservation_id=uuid4(),
            user_id=command.user_id,
            request_key=command.request_key,
            quote_id=quote.id,
            reserved_credit=amount,
            created_at=now,
        )
        info = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
        assert info is not None
        return info


async def _get_owned_reservation(
    session: AsyncSession, user_id: UUID, request_key: UUID, reservation_id: UUID
) -> Types.CreditReservationInfo:
    await _get_credit_balance(session, user_id, for_update=True)
    row = await Repository.get_credit_reservation_by_key(session, user_id, request_key)
    info = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
    if info is None:
        raise Types.CreditReservationNotFoundError("Credit reservation not found.")
    if info.id != reservation_id:
        raise Types.CreditReservationConflictError(
            "Request key belongs to another reservation."
        )
    return info


async def commit_credit_reservation(
    session: AsyncSession, command: Types.CommitCreditReservationCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(
        command.user_id, command.request_key, command.reservation_id, command.result_id
    )
    async with session.begin_nested():
        info = await _get_owned_reservation(
            session, command.user_id, command.request_key, command.reservation_id
        )
        if info.status is Types.CreditReservationStatus.COMMITTED:
            if info.result_id != command.result_id:
                raise Types.CreditReservationConflictError(
                    "Reservation already committed to another result."
                )
            return info
        if info.status is Types.CreditReservationStatus.RELEASED:
            raise Types.CreditReservationConflictError(
                "Released reservations cannot be committed."
            )
        transaction_id = uuid4()
        await Repository.change_credit_balance(
            session,
            command.user_id,
            balance_delta=-info.reserved_credit,
            reserved_delta=-info.reserved_credit,
        )
        await Repository.create_credit_debit(
            session,
            transaction_id=transaction_id,
            user_id=command.user_id,
            request_key=command.request_key,
            result_id=command.result_id,
            amount=info.reserved_credit,
        )
        row = await Repository.finalize_credit_reservation(
            session,
            reservation_id=info.id,
            status=Types.CreditReservationStatus.COMMITTED,
            result_id=command.result_id,
            transaction_id=transaction_id,
            finalized_at=_get_utc_now(),
        )
        result = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
        assert result is not None
        return result


async def release_credit_reservation(
    session: AsyncSession, command: Types.ReleaseCreditReservationCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.reservation_id)
    async with session.begin_nested():
        info = await _get_owned_reservation(
            session, command.user_id, command.request_key, command.reservation_id
        )
        if info.status is Types.CreditReservationStatus.RELEASED:
            return info
        if info.status is Types.CreditReservationStatus.COMMITTED:
            raise Types.CreditReservationConflictError(
                "Committed reservations cannot be released."
            )
        await Repository.change_credit_balance(
            session,
            command.user_id,
            balance_delta=0,
            reserved_delta=-info.reserved_credit,
        )
        row = await Repository.finalize_credit_reservation(
            session,
            reservation_id=info.id,
            status=Types.CreditReservationStatus.RELEASED,
            result_id=None,
            transaction_id=None,
            finalized_at=_get_utc_now(),
        )
        result = CreditPersistenceMapper.credit_reservation_entity_to_info(row)
        assert result is not None
        return result
