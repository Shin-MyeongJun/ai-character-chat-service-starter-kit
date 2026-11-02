"""Server-only credit operations inside an explicit caller-owned transaction."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionTransaction, SessionTransactionOrigin

from app.modules.commerce.credit import repository as Repository
from app.modules.commerce.credit import types as Types
from app.modules.commerce.credit.mapper import persistence as PersistenceMapper

_WRITE_SCOPE_KEY = "credit_write_scope"


@dataclass
class _CreditWriteScope:
    transaction: SessionTransaction
    savepoint: SessionTransaction
    locked_wallets: set[tuple[UUID, str]] = field(default_factory=set)
    failed: bool = False


def _get_credit_write_scope(session: AsyncSession) -> _CreditWriteScope | None:
    scope = session.info.get(_WRITE_SCOPE_KEY)
    if not isinstance(scope, _CreditWriteScope):
        return None
    if (
        session.sync_session.get_transaction() is not scope.transaction
        or not scope.transaction.is_active
        or not scope.savepoint.is_active
    ):
        raise RuntimeError("Credit write scope is no longer active.")
    if session.sync_session.get_nested_transaction() is not scope.savepoint:
        # A caller's independent savepoint owns its own rollback and lock evidence.
        return None
    if scope.failed:
        raise RuntimeError("A joined credit operation failed; scope must roll back.")
    return scope


@asynccontextmanager
async def use_credit_write_scope(session: AsyncSession) -> AsyncIterator[None]:
    """Share one SAVEPOINT for credit writes and caller-owned related persistence.

    The caller still owns the outer transaction. Joined failures poison this scope
    even when caught inside its body. Lock evidence lasts only in this savepoint;
    balances are always read afresh, including after intervening credit writes.
    """
    _require_credit_transaction(session)
    scope = _get_credit_write_scope(session)
    if scope is not None:
        try:
            yield
        except BaseException:
            scope.failed = True
            raise
        return
    previous_scope: object = session.info.get(_WRITE_SCOPE_KEY)
    async with session.begin_nested():
        transaction = session.sync_session.get_transaction()
        savepoint = session.sync_session.get_nested_transaction()
        assert transaction is not None and savepoint is not None
        scope = _CreditWriteScope(transaction, savepoint)
        session.info[_WRITE_SCOPE_KEY] = scope
        try:
            yield
            if _get_credit_write_scope(session) is not scope:
                raise RuntimeError("Credit write scope has an unfinished savepoint.")
        finally:
            if previous_scope is None:
                session.info.pop(_WRITE_SCOPE_KEY, None)
            else:
                session.info[_WRITE_SCOPE_KEY] = previous_scope


def _get_utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_identifiers(*identifiers: UUID) -> None:
    if not all(isinstance(value, UUID) for value in identifiers):
        raise Types.InvalidCreditCommandError("Credit identifiers must be UUIDs.")


def _require_credit_transaction(session: AsyncSession) -> None:
    transaction = session.sync_session.get_transaction()
    if transaction is None or transaction.origin is SessionTransactionOrigin.AUTOBEGIN:
        raise RuntimeError(
            "Credit writes require an explicit caller-owned transaction."
        )


async def _get_credit_balance(
    session: AsyncSession, user_id: UUID, currency_code: str, *, for_update: bool
) -> Types.CreditBalanceInfo:
    _validate_currency(currency_code)
    scope = _get_credit_write_scope(session) if for_update else None
    wallet_key = (user_id, currency_code)
    if scope is None or wallet_key not in scope.locked_wallets:
        if for_update:
            await Repository.lock_credit_wallet(session, user_id, currency_code)
        await _reject_legacy_credit(session, user_id)
    row = await Repository.get_credit_account(session, user_id, currency_code)
    info = PersistenceMapper.credit_account_entity_to_info(row)
    if info is None:
        raise Types.CreditAccountNotFoundError("Credit account not found.")
    if scope is not None:
        scope.locked_wallets.add(wallet_key)
    return info


async def lock_credit_account(
    session: AsyncSession, command: Types.LockCreditAccountCommand
) -> Types.CreditBalanceInfo:
    """Hold the account lock until the caller transaction ends."""
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id)
    return await _get_credit_balance(
        session, command.user_id, command.currency_code, for_update=True
    )


def _validate_metadata(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise Types.InvalidCreditCommandError(
            "Metadata must be a non-empty trimmed string."
        )


async def reserve_credit(
    session: AsyncSession, command: Types.ReserveCreditCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.reference_id)
    for value in (command.namespace, command.reason, command.settlement_key):
        _validate_metadata(value)
    if type(command.amount) is not int or not 0 <= command.amount <= 2**63 - 1:
        raise Types.InvalidCreditCommandError("Amount must be a non-negative bigint.")
    if (
        not isinstance(command.created_at, datetime)
        or command.created_at.utcoffset() is None
    ):
        raise Types.InvalidCreditCommandError(
            "Reservation time must be timezone-aware."
        )
    async with use_credit_write_scope(session):
        balance = await _get_credit_balance(
            session, command.user_id, command.currency_code, for_update=True
        )
        reservation_entity = await Repository.get_credit_reservation_by_key(
            session,
            command.user_id,
            command.namespace,
            command.request_key,
            command.currency_code,
        )
        existing = PersistenceMapper.credit_reservation_entity_to_info(
            reservation_entity
        )
        if existing is not None:
            if (
                existing.reserved_credit,
                existing.reference_id,
                existing.reason,
                existing.settlement_key,
            ) != (
                command.amount,
                command.reference_id,
                command.reason,
                command.settlement_key,
            ):
                raise Types.CreditReservationConflictError(
                    "Request key binds different reservation terms."
                )
            return existing
        if await Repository.has_settlement_key(
            session,
            command.user_id,
            command.currency_code,
            command.namespace,
            command.settlement_key,
        ):
            raise Types.CreditReservationConflictError(
                "Settlement key is already used."
            )
        if balance.available_credit < command.amount:
            raise Types.InsufficientCreditError("Insufficient available credit.")
        free_amount = min(command.amount, balance.free.available_credit)
        paid_amount = command.amount - free_amount
        for bucket, amount in (("free", free_amount), ("paid", paid_amount)):
            await Repository.change_credit_balance(
                session,
                command.user_id,
                command.currency_code,
                bucket=bucket,
                balance_delta=0,
                reserved_delta=amount,
            )
        reservation_entity = await Repository.create_credit_reservation(
            session,
            reservation_id=uuid4(),
            currency_code=command.currency_code,
            free_amount=free_amount,
            paid_amount=paid_amount,
            user_id=command.user_id,
            namespace=command.namespace,
            request_key=command.request_key,
            reference_id=command.reference_id,
            reason=command.reason,
            settlement_key=command.settlement_key,
            reserved_credit=command.amount,
            created_at=command.created_at,
        )
        info = PersistenceMapper.credit_reservation_entity_to_info(reservation_entity)
        assert info is not None
        return info


async def _get_owned_reservation(
    session: AsyncSession,
    user_id: UUID,
    namespace: str,
    request_key: UUID,
    reservation_id: UUID,
    currency_code: str,
) -> Types.CreditReservationInfo:
    await _get_credit_balance(session, user_id, currency_code, for_update=True)
    reservation_entity = await Repository.get_credit_reservation_by_key(
        session, user_id, namespace, request_key, currency_code
    )
    info = PersistenceMapper.credit_reservation_entity_to_info(reservation_entity)
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
    _validate_metadata(command.namespace)
    async with use_credit_write_scope(session):
        info = await _get_owned_reservation(
            session,
            command.user_id,
            command.namespace,
            command.request_key,
            command.reservation_id,
            command.currency_code,
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
        assert info.free_amount is not None and info.paid_amount is not None
        for bucket, amount in (("free", info.free_amount), ("paid", info.paid_amount)):
            await Repository.change_credit_balance(
                session,
                command.user_id,
                command.currency_code,
                bucket=bucket,
                balance_delta=-amount,
                reserved_delta=-amount,
            )
        await Repository.create_credit_debit(
            session,
            transaction_id=transaction_id,
            user_id=command.user_id,
            currency_code=command.currency_code,
            namespace=command.namespace,
            request_key=command.request_key,
            reason=info.reason,
            key=info.settlement_key,
            reference_id=command.result_id,
            free_amount=-info.free_amount,
            paid_amount=-info.paid_amount,
        )
        reservation_entity = await Repository.finalize_credit_reservation(
            session,
            reservation_id=info.id,
            status=Types.CreditReservationStatus.COMMITTED,
            result_id=command.result_id,
            transaction_id=transaction_id,
            finalized_at=_get_utc_now(),
        )
        result = PersistenceMapper.credit_reservation_entity_to_info(reservation_entity)
        assert result is not None
        return result


async def release_credit_reservation(
    session: AsyncSession, command: Types.ReleaseCreditReservationCommand
) -> Types.CreditReservationInfo:
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.reservation_id)
    _validate_metadata(command.namespace)
    async with use_credit_write_scope(session):
        info = await _get_owned_reservation(
            session,
            command.user_id,
            command.namespace,
            command.request_key,
            command.reservation_id,
            command.currency_code,
        )
        if info.status is Types.CreditReservationStatus.RELEASED:
            return info
        if info.status is Types.CreditReservationStatus.COMMITTED:
            raise Types.CreditReservationConflictError(
                "Committed reservations cannot be released."
            )
        assert info.free_amount is not None and info.paid_amount is not None
        for bucket, amount in (("free", info.free_amount), ("paid", info.paid_amount)):
            await Repository.change_credit_balance(
                session,
                command.user_id,
                command.currency_code,
                bucket=bucket,
                balance_delta=0,
                reserved_delta=-amount,
            )
        reservation_entity = await Repository.finalize_credit_reservation(
            session,
            reservation_id=info.id,
            status=Types.CreditReservationStatus.RELEASED,
            result_id=None,
            transaction_id=None,
            finalized_at=_get_utc_now(),
        )
        result = PersistenceMapper.credit_reservation_entity_to_info(reservation_entity)
        assert result is not None
        return result


def _validate_currency(currency_code: str) -> None:
    if (
        not isinstance(currency_code, str)
        or re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", currency_code) is None
    ):
        raise Types.InvalidCreditCommandError("Invalid currency code.")


async def _reject_legacy_credit(session: AsyncSession, user_id: UUID) -> None:
    if await Repository.has_legacy_credit(session, user_id):
        raise Types.CreditClassificationRequiredError(
            "Unclassified legacy credit requires approved classification "
            "before activation."
        )


async def prepare_credit_wallet(
    session: AsyncSession, command: Types.PrepareCreditWalletCommand
) -> Types.CreditBalanceInfo:
    """Server-authorized preparation only; no implicit legacy conversion or grant."""
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id)
    _validate_currency(command.currency_code)
    async with session.begin_nested():
        await Repository.lock_credit_wallet(
            session, command.user_id, command.currency_code
        )
        await _reject_legacy_credit(session, command.user_id)
        row = await Repository.get_credit_account(
            session, command.user_id, command.currency_code
        )
        existing = PersistenceMapper.credit_account_entity_to_info(row)
        if existing is not None:
            return existing
        await Repository.create_credit_wallet(
            session, command.user_id, command.currency_code
        )
        return await _get_credit_balance(
            session, command.user_id, command.currency_code, for_update=False
        )


async def grant_credit(
    session: AsyncSession, command: Types.GrantCreditCommand
) -> Types.CreditTransactionInfo:
    """Internal trusted-server grant. PAID is not proof of a cash payment."""
    _require_credit_transaction(session)
    _validate_identifiers(command.user_id, command.request_key, command.reference_id)
    _validate_currency(command.currency_code)
    for value in (command.namespace, command.reason):
        _validate_metadata(value)
    if not isinstance(command.bucket, Types.CreditBucket):
        raise Types.InvalidCreditCommandError("Grant bucket must be FREE or PAID.")
    if type(command.amount) is not int or not 1 <= command.amount <= 2**63 - 1:
        raise Types.InvalidCreditCommandError("Grant amount must be a positive bigint.")
    async with session.begin_nested():
        balance = await prepare_credit_wallet(
            session,
            Types.PrepareCreditWalletCommand(
                user_id=command.user_id,
                currency_code=command.currency_code,
            ),
        )
        row = await Repository.get_credit_grant(
            session,
            command.user_id,
            command.currency_code,
            command.namespace,
            command.request_key,
        )
        existing = PersistenceMapper.credit_transaction_row_to_info(row)
        free_amount = command.amount if command.bucket is Types.CreditBucket.FREE else 0
        paid_amount = command.amount if command.bucket is Types.CreditBucket.PAID else 0
        if existing is not None:
            if (
                existing.free_amount,
                existing.paid_amount,
                existing.reason,
                existing.reference_id,
            ) != (free_amount, paid_amount, command.reason, command.reference_id):
                raise Types.CreditGrantConflictError("Grant key binds different terms.")
            return existing
        if balance.balance_credit + command.amount > 2**63 - 1:
            raise Types.InvalidCreditCommandError(
                "Grant exceeds currency bigint capacity."
            )
        await Repository.change_credit_balance(
            session,
            command.user_id,
            command.currency_code,
            bucket=command.bucket,
            balance_delta=command.amount,
            reserved_delta=0,
        )
        row = await Repository.create_credit_movement(
            session,
            transaction_id=uuid4(),
            user_id=command.user_id,
            currency_code=command.currency_code,
            namespace=command.namespace,
            request_key=command.request_key,
            operation="grant",
            reason=command.reason,
            key=str(command.request_key),
            reference_id=command.reference_id,
            free_amount=free_amount,
            paid_amount=paid_amount,
        )
        info = PersistenceMapper.credit_transaction_row_to_info(row)
        assert info is not None
        return info
