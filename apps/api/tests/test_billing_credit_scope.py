"""PostgreSQL contracts for the shared billing/credit savepoint and wallet locks."""

import asyncio
from collections import Counter
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from credit_support import fund_credit
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from test_billing_credits import (
    NOW,
    _assert_credit_state,
    _commit_command,
    _credit_fixture,  # noqa: F401
    _invoke_credit,
    _release_command,
    _reserve_credit,
)
from test_billing_prices import _configuration, _request_info  # noqa: F401
from test_credit_services import _invoke
from test_credit_services import credit_command as credit_command

from app.db.models.credit import CreditBalance, CreditReservation
from app.modules.commerce.billing import repository as BillingRepository
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingService
from app.modules.commerce.credit import repository as CreditRepository
from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import command as CreditService


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reserve", "replay", "commit", "release"])
async def test_billing_operation_uses_one_savepoint_and_one_wallet_lock(
    db: AsyncSession, credit_fixture: BillingTypes.ReserveCreditCommand, action: str
) -> None:
    reservation = (
        None if action == "reserve" else await _reserve_credit(db, credit_fixture)
    )
    counts: Counter[str] = Counter()

    def count_sql(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        sql = statement.lower()
        counts["sql"] += 1
        if sql.startswith("savepoint "):
            counts["savepoint"] += 1
        if sql.startswith("release savepoint "):
            counts["release_savepoint"] += 1
        if "pg_advisory_xact_lock" in sql:
            counts["advisory"] += 1
        if "from credit_wallets" in sql and "for update" in sql:
            counts["wallet_lock"] += 1
        if "from credit_accounts" in sql:
            counts["legacy_check"] += 1

    assert isinstance(db.bind, AsyncEngine)
    engine = db.bind.sync_engine
    event.listen(engine, "before_cursor_execute", count_sql)
    try:
        if action in ("reserve", "replay"):
            await _reserve_credit(db, credit_fixture)
        elif action == "commit":
            await _invoke_credit(
                db,
                BillingService.commit_credit_reservation,
                _commit_command(reservation),
            )
        else:
            await _invoke_credit(
                db,
                BillingService.release_credit_reservation,
                _release_command(reservation),
            )
    finally:
        event.remove(engine, "before_cursor_execute", count_sql)
    print(f"U21 {action}: {dict(counts)}")
    assert counts["savepoint"] == counts["release_savepoint"] == 1
    # Billing request key and credit wallet protect distinct identities.
    assert counts["advisory"] == 2
    assert counts["wallet_lock"] == counts["legacy_check"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reserve", "commit", "release"])
@pytest.mark.parametrize("failure_kind", ["sql", "cancel"])
async def test_shared_savepoint_recovers_after_partial_write_and_retries_same_key(
    db: AsyncSession,
    credit_fixture: BillingTypes.ReserveCreditCommand,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    failure_kind: str,
) -> None:
    reservation = (
        None if action == "reserve" else await _reserve_credit(db, credit_fixture)
    )
    commit = _commit_command(reservation) if reservation is not None else None

    async def invoke() -> BillingTypes.CreditReservationInfo:
        if action == "reserve":
            return await BillingService.reserve_credit(
                db, credit_fixture, clock=lambda: NOW
            )
        if action == "commit":
            assert commit is not None
            return await BillingService.commit_credit_reservation(db, commit)
        return await BillingService.release_credit_reservation(
            db, _release_command(reservation)
        )

    async def fail_after_writes(session: AsyncSession, **kwargs: object) -> None:
        if failure_kind == "cancel":
            raise asyncio.CancelledError()
        # A real PostgreSQL error aborts the savepoint, unlike a Python-only stub.
        await session.execute(text("SELECT 1 / 0"))

    async with db.begin():
        with monkeypatch.context() as patch:
            patch.setattr(
                BillingRepository if action == "reserve" else CreditRepository,
                "create_credit_binding"
                if action == "reserve"
                else "finalize_credit_reservation",
                fail_after_writes,
            )
            with pytest.raises(
                DBAPIError if failure_kind == "sql" else asyncio.CancelledError
            ):
                await invoke()
        # Catching the error must leave the outer transaction usable and unchanged.
        assert await db.scalar(text("SELECT 1")) == 1
        balance, reserved = (
            await db.execute(
                select(
                    func.sum(CreditBalance.balance),
                    func.sum(CreditBalance.reserved_credit),
                )
            )
        ).one()
        assert (balance, reserved) == (20, 0 if action == "reserve" else 10)
        result = await invoke()
        if reservation is not None:
            assert result.id == reservation.id
    await _assert_credit_state(
        db,
        credit_fixture.user_id,
        balance=10 if action == "commit" else 20,
        reserved=10 if action == "reserve" else 0,
        reservations=1,
        debits=int(action == "commit"),
    )


@pytest.mark.asyncio
async def test_caught_joined_failure_rolls_back_whole_scope_but_not_outer_transaction(
    db: AsyncSession, credit_command: CreditTypes.ReserveCreditCommand
) -> None:
    second = replace(
        credit_command, request_key=uuid4(), settlement_key=str(uuid4()), amount=15
    )
    async with db.begin():
        with pytest.raises(RuntimeError, match="scope must roll back"):
            async with CreditService.use_credit_write_scope(db):
                await CreditService.reserve_credit(db, credit_command)
                with pytest.raises(CreditTypes.InsufficientCreditError):
                    await CreditService.reserve_credit(db, second)
                with pytest.raises(RuntimeError, match="scope must roll back"):
                    await CreditService.reserve_credit(db, credit_command)
        assert await db.scalar(select(func.count()).select_from(CreditReservation)) == 0
        assert await db.scalar(select(func.sum(CreditBalance.reserved_credit))) == 0
        # The same outer transaction can use a fresh scope and the original key.
        await CreditService.reserve_credit(db, credit_command)
    await _assert_credit_state(
        db, credit_command.user_id, balance=20, reserved=10, reservations=1, debits=0
    )


@pytest.mark.asyncio
async def test_shared_lock_rereads_balance_after_reservation_and_grant(
    db: AsyncSession, credit_command: CreditTypes.ReserveCreditCommand
) -> None:
    async with db.begin(), CreditService.use_credit_write_scope(db):
        first = await CreditService.reserve_credit(
            db, replace(credit_command, amount=15)
        )
        await fund_credit(
            db, credit_command.user_id, 10, bucket=CreditTypes.CreditBucket.PAID
        )
        second = await CreditService.reserve_credit(
            db,
            replace(credit_command, request_key=uuid4(), settlement_key=str(uuid4())),
        )
        assert (first.free_amount, first.paid_amount) == (15, 0)
        assert (second.free_amount, second.paid_amount) == (5, 5)
    await _assert_credit_state(
        db, credit_command.user_id, balance=30, reserved=25, reservations=2, debits=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["user", "currency"])
async def test_shared_lock_does_not_authorize_another_wallet(
    db: AsyncSession, credit_command: CreditTypes.ReserveCreditCommand, mismatch: str
) -> None:
    command = (
        replace(credit_command, user_id=uuid4())
        if mismatch == "user"
        else replace(credit_command, currency_code="OTHER")
    )
    async with db.begin():
        with pytest.raises(CreditTypes.CreditAccountNotFoundError):
            async with CreditService.use_credit_write_scope(db):
                await CreditService.lock_credit_account(
                    db,
                    CreditTypes.LockCreditAccountCommand(
                        user_id=credit_command.user_id,
                        currency_code=credit_command.currency_code,
                    ),
                )
                await CreditService.reserve_credit(db, command)
    await _assert_credit_state(
        db, credit_command.user_id, balance=20, reserved=0, reservations=0, debits=0
    )


@pytest.mark.asyncio
async def test_rolled_back_child_scope_does_not_leave_wallet_lock_evidence(
    db: AsyncSession,
    credit_command: CreditTypes.ReserveCreditCommand,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = CreditRepository.lock_credit_wallet
    locks = 0

    async def lock_wallet(
        session: AsyncSession, user_id: UUID, currency_code: str
    ) -> None:
        nonlocal locks
        locks += 1
        await original(session, user_id, currency_code)

    monkeypatch.setattr(CreditRepository, "lock_credit_wallet", lock_wallet)
    async with db.begin(), CreditService.use_credit_write_scope(db):
        with pytest.raises(RuntimeError, match="discard child"):
            async with db.begin_nested():
                await CreditService.reserve_credit(db, credit_command)
                raise RuntimeError("discard child")
        await CreditService.reserve_credit(db, credit_command)
    assert locks == 2
    # A new transaction on the same session must acquire the lock again.
    async with db.begin():
        await CreditService.reserve_credit(db, credit_command)
    assert locks == 3
    await _assert_credit_state(
        db, credit_command.user_id, balance=20, reserved=10, reservations=1, debits=0
    )


@pytest.mark.asyncio
async def test_billing_and_standalone_credit_race_cannot_overspend(
    db: AsyncSession, credit_fixture: BillingTypes.ReserveCreditCommand
) -> None:
    command = CreditTypes.ReserveCreditCommand(
        user_id=credit_fixture.user_id,
        currency_code="CREDIT",
        namespace="standalone",
        request_key=uuid4(),
        amount=15,
        reference_id=uuid4(),
        reason="export",
        settlement_key=str(uuid4()),
        created_at=NOW,
    )
    barrier = asyncio.Barrier(2)

    async def reserve_billing() -> BillingTypes.CreditReservationInfo:
        await barrier.wait()
        return await _reserve_credit(db, credit_fixture)

    async def reserve_standalone() -> CreditTypes.CreditReservationInfo:
        await barrier.wait()
        return await _invoke(db, CreditService.reserve_credit, command)

    results = await asyncio.wait_for(
        asyncio.gather(reserve_billing(), reserve_standalone(), return_exceptions=True),
        15,
    )
    assert (
        sum(
            isinstance(
                item,
                (
                    BillingTypes.InsufficientCreditError,
                    CreditTypes.InsufficientCreditError,
                ),
            )
            for item in results
        )
        == 1
    )
    winner = next(item for item in results if not isinstance(item, BaseException))
    await _assert_credit_state(
        db,
        command.user_id,
        balance=20,
        reserved=winner.reserved_credit,
        reservations=1,
        debits=0,
    )
