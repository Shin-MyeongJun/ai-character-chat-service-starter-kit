"""Credit-owned persistence. Wallet lock precedes all balance/ledger writes."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.models.credit import (
    CreditAccount,
    CreditBalance,
    CreditReservation,
    CreditTransaction,
    CreditTransactionEntry,
    CreditWallet,
)


@dataclass
class CreditWalletRow:
    wallet: CreditWallet | None
    balances: list[CreditBalance]


@dataclass
class CreditTransactionRow:
    transaction: CreditTransaction
    entries: list[CreditTransactionEntry]


async def has_legacy_credit(session: AsyncSession, user_id: UUID) -> bool:
    return bool(
        await session.scalar(
            select(
                select(CreditAccount.user_id)
                .where(CreditAccount.user_id == user_id)
                .exists()
                | select(CreditTransaction.id)
                .where(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.operation == "legacy",
                )
                .exists()
                | select(CreditReservation.id)
                .where(
                    CreditReservation.user_id == user_id,
                    CreditReservation.currency_code.is_(None),
                )
                .exists()
            )
        )
    )


async def lock_credit_wallet(
    session: AsyncSession, user_id: UUID, currency_code: str
) -> None:
    await lock_key(session, "credit-wallet", f"{user_id}:{currency_code}")
    await session.scalar(
        select(CreditWallet)
        .where(
            CreditWallet.user_id == user_id, CreditWallet.currency_code == currency_code
        )
        .with_for_update()
    )


async def create_credit_wallet(
    session: AsyncSession, user_id: UUID, currency_code: str
) -> None:
    await session.execute(
        insert(CreditWallet)
        .values(user_id=user_id, currency_code=currency_code)
        .on_conflict_do_nothing()
    )
    for bucket in ("free", "paid"):
        await session.execute(
            insert(CreditBalance)
            .values(user_id=user_id, currency_code=currency_code, bucket=bucket)
            .on_conflict_do_nothing()
        )


async def get_credit_account(
    session: AsyncSession,
    user_id: UUID,
    currency_code: str,
    *,
    for_update: bool = False,
) -> CreditWalletRow:
    if for_update:
        await lock_credit_wallet(session, user_id, currency_code)
    # One snapshot for both buckets, including a malformed/empty wallet.
    rows = (
        await session.execute(
            select(CreditWallet, CreditBalance)
            .outerjoin(
                CreditBalance,
                (CreditWallet.user_id == CreditBalance.user_id)
                & (CreditWallet.currency_code == CreditBalance.currency_code),
            )
            .where(
                CreditWallet.user_id == user_id,
                CreditWallet.currency_code == currency_code,
            )
            .order_by(CreditBalance.bucket)
            .execution_options(populate_existing=True)
        )
    ).all()
    return CreditWalletRow(
        rows[0][0] if rows else None, [r[1] for r in rows if r[1] is not None]
    )


async def get_credit_reservation_by_key(
    session: AsyncSession,
    user_id: UUID,
    namespace: str,
    request_key: UUID,
    currency_code: str,
    *,
    for_update: bool = True,
) -> CreditReservation | None:
    statement = select(CreditReservation).where(
        CreditReservation.user_id == user_id,
        CreditReservation.request_key == request_key,
        CreditReservation.namespace == namespace,
        CreditReservation.currency_code == currency_code,
    )
    if for_update:
        statement = statement.with_for_update()
    return await session.scalar(statement.execution_options(populate_existing=True))


async def has_settlement_key(
    session: AsyncSession, user_id: UUID, currency_code: str, namespace: str, key: str
) -> bool:
    return bool(
        await session.scalar(
            select(
                select(CreditReservation.id)
                .where(
                    CreditReservation.user_id == user_id,
                    CreditReservation.currency_code == currency_code,
                    CreditReservation.namespace == namespace,
                    CreditReservation.settlement_key == key,
                )
                .exists()
                | select(CreditTransaction.id)
                .where(
                    CreditTransaction.user_id == user_id,
                    CreditTransaction.currency_code == currency_code,
                    CreditTransaction.namespace == namespace,
                    CreditTransaction.operation == "consume",
                    CreditTransaction.idempotency_key == key,
                )
                .exists()
            )
        )
    )


async def change_credit_balance(
    session: AsyncSession,
    user_id: UUID,
    currency_code: str,
    *,
    bucket: str,
    balance_delta: int,
    reserved_delta: int,
) -> None:
    result = await session.execute(
        update(CreditBalance)
        .where(
            CreditBalance.user_id == user_id,
            CreditBalance.currency_code == currency_code,
            CreditBalance.bucket == bucket,
        )
        .values(
            balance=CreditBalance.balance + balance_delta,
            reserved_credit=CreditBalance.reserved_credit + reserved_delta,
        )
        .returning(CreditBalance.bucket)
    )
    if result.scalar_one_or_none() is None:
        raise RuntimeError("Incomplete credit wallet.")


async def create_credit_reservation(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    user_id: UUID,
    request_key: UUID,
    namespace: str,
    reference_id: UUID,
    reason: str,
    settlement_key: str,
    reserved_credit: int,
    created_at: datetime,
    currency_code: str,
    free_amount: int,
    paid_amount: int,
) -> CreditReservation:
    entity = CreditReservation(
        id=reservation_id,
        user_id=user_id,
        request_key=request_key,
        namespace=namespace,
        reference_id=reference_id,
        reason=reason,
        settlement_key=settlement_key,
        reserved_credit=reserved_credit,
        status="reserved",
        created_at=created_at,
        currency_code=currency_code,
        free_amount=free_amount,
        paid_amount=paid_amount,
        allocation_status="allocated",
    )
    session.add(entity)
    await session.flush()
    return entity


async def create_credit_movement(
    session: AsyncSession,
    *,
    transaction_id: UUID,
    user_id: UUID,
    currency_code: str,
    namespace: str,
    request_key: UUID,
    operation: str,
    reason: str,
    key: str,
    reference_id: UUID,
    free_amount: int,
    paid_amount: int,
) -> CreditTransactionRow:
    entity = CreditTransaction(
        id=transaction_id,
        user_id=user_id,
        currency_code=currency_code,
        namespace=namespace,
        request_key=request_key,
        operation=operation,
        amount=free_amount + paid_amount,
        reason=reason,
        reference_id=reference_id,
        idempotency_key=key,
    )
    session.add(entity)
    await session.flush()
    entries = [
        CreditTransactionEntry(
            transaction_id=transaction_id,
            user_id=user_id,
            currency_code=currency_code,
            bucket=bucket,
            amount=amount,
        )
        for bucket, amount in (("free", free_amount), ("paid", paid_amount))
        if amount
    ]
    session.add_all(entries)
    await session.flush()
    return CreditTransactionRow(entity, entries)


async def create_credit_debit(session: AsyncSession, **values) -> None:
    await create_credit_movement(session, operation="consume", **values)


async def get_credit_grant(
    session: AsyncSession,
    user_id: UUID,
    currency_code: str,
    namespace: str,
    request_key: UUID,
) -> CreditTransactionRow | None:
    entity = await session.scalar(
        select(CreditTransaction).where(
            CreditTransaction.user_id == user_id,
            CreditTransaction.currency_code == currency_code,
            CreditTransaction.namespace == namespace,
            CreditTransaction.operation == "grant",
            CreditTransaction.request_key == request_key,
        )
    )
    if entity is None:
        return None
    entries = list(
        await session.scalars(
            select(CreditTransactionEntry).where(
                CreditTransactionEntry.transaction_id == entity.id
            )
        )
    )
    return CreditTransactionRow(entity, entries)


def _history_statement(
    model,
    *,
    user_id,
    currency_code,
    namespace,
    reason,
    start,
    end,
    cursor,
    limit,
    status=None,
):
    statement = select(model).where(
        model.user_id == user_id, model.currency_code == currency_code
    )
    for column, value in ((model.namespace, namespace), (model.reason, reason)):
        if value is not None:
            statement = statement.where(column == value)
    if start is not None:
        statement = statement.where(model.created_at >= start)
    if end is not None:
        statement = statement.where(model.created_at < end)
    if cursor is not None:
        statement = statement.where(tuple_(model.created_at, model.id) < cursor)
    if status is not None:
        statement = statement.where(model.status == status)
    return statement.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)


async def list_credit_transactions(
    session: AsyncSession, **filters
) -> list[CreditTransactionRow]:
    entities = list(
        await session.scalars(_history_statement(CreditTransaction, **filters))
    )
    entries = (
        list(
            await session.scalars(
                select(CreditTransactionEntry).where(
                    CreditTransactionEntry.transaction_id.in_(
                        [entity.id for entity in entities]
                    )
                )
            )
        )
        if entities
        else []
    )
    return [
        CreditTransactionRow(
            entity, [e for e in entries if e.transaction_id == entity.id]
        )
        for entity in entities
    ]


async def list_credit_reservations(
    session: AsyncSession, **filters
) -> list[CreditReservation]:
    return list(await session.scalars(_history_statement(CreditReservation, **filters)))


async def finalize_credit_reservation(
    session: AsyncSession,
    *,
    reservation_id: UUID,
    status: str,
    result_id: UUID | None,
    transaction_id: UUID | None,
    finalized_at: datetime,
) -> CreditReservation:
    result = await session.scalars(
        update(CreditReservation)
        .where(CreditReservation.id == reservation_id)
        .values(
            status=status,
            result_id=result_id,
            transaction_id=transaction_id,
            finalized_at=finalized_at,
        )
        .returning(CreditReservation)
        .execution_options(populate_existing=True)
    )
    return result.one()
