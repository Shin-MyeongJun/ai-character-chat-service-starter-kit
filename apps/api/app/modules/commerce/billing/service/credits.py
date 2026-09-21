"""Billing quote validation and compatibility adapter to public credit services."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransactionOrigin

from app.db.idempotency import lock_key
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import credits as CreditPersistenceMapper
from app.modules.commerce.billing.service import quotes as QuoteService
from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import command as CreditCommandService
from app.modules.commerce.credit.service import query as CreditQueryService


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


@contextmanager
def _translate_credit_errors() -> Iterator[None]:
    try:
        yield
    except CreditTypes.CreditAccountNotFoundError as error:
        raise Types.CreditAccountNotFoundError(str(error)) from error
    except CreditTypes.InsufficientCreditError as error:
        raise Types.InsufficientCreditError(str(error)) from error
    except CreditTypes.CreditReservationNotFoundError as error:
        raise Types.CreditReservationNotFoundError(str(error)) from error
    except (
        CreditTypes.CreditReservationConflictError,
        CreditTypes.InvalidCreditCommandError,
    ) as error:
        raise Types.CreditReservationConflictError(str(error)) from error


async def get_credit_balance(
    session: AsyncSession, command: Types.GetCreditBalanceCommand
) -> Types.CreditBalanceInfo:
    with _translate_credit_errors():
        info = await CreditQueryService.get_credit_balance(
            session,
            CreditTypes.GetCreditBalanceCommand(
                user_id=command.user_id, currency_code="CREDIT"
            ),
        )
    return CreditPersistenceMapper.credit_balance_info_to_info(info)


async def _lock_credit_account(
    session: AsyncSession, user_id: UUID, request_key: UUID
) -> None:
    # Same ordering as quote creation, before the credit-owned account lock.
    await lock_key(session, "billing-quote", f"{user_id}:{request_key}")
    await CreditCommandService.lock_credit_account(
        session,
        CreditTypes.LockCreditAccountCommand(user_id=user_id, currency_code="CREDIT"),
    )


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
    with _translate_credit_errors():
        async with session.begin_nested():
            await _lock_credit_account(session, command.user_id, command.request_key)
            now = QuoteService._get_quote_time(clock)
            row = await Repository.get_credit_binding(
                session, command.user_id, command.request_key
            )
            binding = CreditPersistenceMapper.credit_binding_entity_to_info(row)
            if binding is not None and binding.quote_id != command.quote_id:
                raise Types.CreditReservationConflictError(
                    "Request key already binds another quote."
                )
            quote = await QuoteService.get_billing_quote(
                session,
                Types.GetBillingQuoteCommand(
                    quote_id=command.quote_id, request=command.request
                ),
                clock=lambda: now,
            )
            if binding is not None:
                info = await CreditQueryService.get_credit_reservation(
                    session,
                    CreditTypes.GetCreditReservationCommand(
                        user_id=command.user_id,
                        namespace="billing",
                        currency_code="CREDIT",
                        request_key=command.request_key,
                    ),
                )
                if (
                    info is None
                    or info.id != binding.reservation_id
                    or info.currency_code != "CREDIT"
                    or info.reserved_credit != quote.price.final_price_credit
                    or info.allocation_status != "allocated"
                ):
                    raise Types.CreditReservationConflictError(
                        "Reservation binding is inconsistent."
                    )
                return CreditPersistenceMapper.credit_reservation_binding_infos_to_info(
                    info, binding
                )
            row = await Repository.get_credit_binding_by_quote(session, quote.id)
            if CreditPersistenceMapper.credit_binding_entity_to_info(row) is not None:
                raise Types.CreditReservationConflictError(
                    "Quote has already been used."
                )
            if quote.status is Types.BillingQuoteStatus.EXPIRED:
                raise Types.BillingQuoteExpiredError(
                    "Billing quote expired; obtain a new quote."
                )
            info = await CreditCommandService.reserve_credit(
                session,
                CreditTypes.ReserveCreditCommand(
                    user_id=command.user_id,
                    namespace="billing",
                    currency_code="CREDIT",
                    request_key=command.request_key,
                    amount=quote.price.final_price_credit,
                    reference_id=uuid4(),
                    reason="chat_usage",
                    settlement_key=f"billing:credit-settlement:{command.user_id}:{command.request_key}",
                    created_at=now,
                ),
            )
            row = await Repository.create_credit_binding(
                session,
                reservation_id=info.id,
                quote_id=quote.id,
                user_id=command.user_id,
                request_key=command.request_key,
                created_at=now,
            )
            binding = CreditPersistenceMapper.credit_binding_entity_to_info(row)
            assert binding is not None
            return CreditPersistenceMapper.credit_reservation_binding_infos_to_info(
                info, binding
            )


async def _get_owned_binding(
    session: AsyncSession,
    user_id: UUID,
    request_key: UUID,
    reservation_id: UUID,
) -> Types.CreditBindingInfo:
    await _lock_credit_account(session, user_id, request_key)
    row = await Repository.get_credit_binding(session, user_id, request_key)
    binding = CreditPersistenceMapper.credit_binding_entity_to_info(row)
    if binding is None:
        raise Types.CreditReservationNotFoundError("Credit reservation not found.")
    if binding.reservation_id != reservation_id:
        raise Types.CreditReservationConflictError(
            "Request key belongs to another reservation."
        )
    return binding


async def commit_credit_reservation(
    session: AsyncSession, command: Types.CommitCreditReservationCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(
        command.user_id, command.request_key, command.reservation_id, command.result_id
    )
    with _translate_credit_errors():
        async with session.begin_nested():
            binding = await _get_owned_binding(
                session, command.user_id, command.request_key, command.reservation_id
            )
            info = await CreditCommandService.commit_credit_reservation(
                session,
                CreditTypes.CommitCreditReservationCommand(
                    user_id=command.user_id,
                    namespace="billing",
                    currency_code="CREDIT",
                    request_key=command.request_key,
                    reservation_id=command.reservation_id,
                    result_id=command.result_id,
                ),
            )
            return CreditPersistenceMapper.credit_reservation_binding_infos_to_info(
                info, binding
            )


async def release_credit_reservation(
    session: AsyncSession, command: Types.ReleaseCreditReservationCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.reservation_id)
    with _translate_credit_errors():
        async with session.begin_nested():
            binding = await _get_owned_binding(
                session, command.user_id, command.request_key, command.reservation_id
            )
            info = await CreditCommandService.release_credit_reservation(
                session,
                CreditTypes.ReleaseCreditReservationCommand(
                    user_id=command.user_id,
                    namespace="billing",
                    currency_code="CREDIT",
                    request_key=command.request_key,
                    reservation_id=command.reservation_id,
                ),
            )
            return CreditPersistenceMapper.credit_reservation_binding_infos_to_info(
                info, binding
            )
