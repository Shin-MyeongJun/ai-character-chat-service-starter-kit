"""Real PostgreSQL, UUID-isolated schemas, separate sessions for concurrent calls."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.models.billing import CreditAccount, CreditTransaction
from app.db.models.billing_credit import CreditReservation
from app.db.models.identity import User
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.service import credits as CreditService
from app.modules.commerce.billing.service import quotes as QuoteService
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_billing_prices import _configuration, _request_info  # noqa: F401

NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest_asyncio.fixture
async def credit_fixture(db, request_info, configuration):
    async with db.begin():
        db.add(
            User(id=request_info.user_id, email=f"{request_info.user_id}@credit.test")
        )
        await db.flush()
        # No production grant/charge API: only this fixture initializes credit.
        db.add(CreditAccount(user_id=request_info.user_id, balance=20))
        db.add(
            CreditTransaction(
                user_id=request_info.user_id,
                amount=20,
                reason="purchase",
                idempotency_key=f"fixture:{request_info.user_id}",
            )
        )
    quote = await QuoteService.create_billing_quote(
        db,
        Types.CreateBillingQuoteCommand(request=request_info),
        configuration=configuration,
        clock=lambda: NOW,
    )
    return Types.ReserveCreditCommand(
        user_id=request_info.user_id,
        request_key=request_info.request_key,
        quote_id=quote.id,
        request=request_info,
    )


async def _invoke_credit(db, service, command, **kwargs):
    async with AsyncSession(db.bind, expire_on_commit=False) as session:
        async with session.begin():
            return await service(session, command, **kwargs)


async def _reserve_credit(db, command, *, now=NOW):
    return await _invoke_credit(
        db, CreditService.reserve_credit, command, clock=lambda: now
    )


def _commit_command(info, result_id=None):
    return Types.CommitCreditReservationCommand(
        user_id=info.user_id,
        request_key=info.request_key,
        reservation_id=info.id,
        result_id=result_id or uuid4(),
    )


def _release_command(info):
    return Types.ReleaseCreditReservationCommand(
        user_id=info.user_id, request_key=info.request_key, reservation_id=info.id
    )


async def _assert_credit_state(db, user_id, *, balance, reserved, reservations, debits):
    async with AsyncSession(db.bind) as session:
        info = await CreditService.get_credit_balance(
            session, Types.GetCreditBalanceCommand(user_id=user_id)
        )
        assert info == Types.CreditBalanceInfo(
            user_id=user_id,
            balance_credit=balance,
            reserved_credit=reserved,
            available_credit=balance - reserved,
        )
        assert (
            await session.scalar(select(func.count()).select_from(CreditReservation))
            == reservations
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CreditTransaction)
                .where(CreditTransaction.reason == "chat_usage")
            )
            == debits
        )
        assert (
            await session.scalar(
                select(func.coalesce(func.sum(CreditTransaction.amount), 0))
            )
            == balance
        )
        assert (
            await session.scalar(
                select(
                    func.coalesce(func.sum(CreditReservation.reserved_credit), 0)
                ).where(CreditReservation.status == "reserved")
            )
            == reserved
        )


@pytest.mark.asyncio
async def test_insufficient_credit_has_no_partial_writes(db, credit_fixture):
    async with db.begin():
        await db.execute(update(CreditAccount).values(balance=9))
        await db.execute(update(CreditTransaction).values(amount=9))
    with pytest.raises(Types.InsufficientCreditError):
        await _reserve_credit(db, credit_fixture)
    await _assert_credit_state(
        db, credit_fixture.user_id, balance=9, reserved=0, reservations=0, debits=0
    )


@pytest.mark.asyncio
async def test_concurrent_reservations_cannot_overspend(
    db, credit_fixture, configuration
):
    commands = [credit_fixture]
    for _ in range(5):
        request = replace(credit_fixture.request, request_key=uuid4())
        quote = await QuoteService.create_billing_quote(
            db,
            Types.CreateBillingQuoteCommand(request=request),
            configuration=configuration,
            clock=lambda: NOW,
        )
        commands.append(
            replace(
                credit_fixture,
                request_key=request.request_key,
                quote_id=quote.id,
                request=request,
            )
        )
    barrier = asyncio.Barrier(len(commands))

    async def reserve(command):
        await barrier.wait()
        return await _reserve_credit(db, command)

    outcomes = await asyncio.wait_for(
        asyncio.gather(*(reserve(c) for c in commands), return_exceptions=True), 15
    )
    assert sum(isinstance(o, Types.CreditReservationInfo) for o in outcomes) == 2
    assert sum(isinstance(o, Types.InsufficientCreditError) for o in outcomes) == 4
    await _assert_credit_state(
        db, credit_fixture.user_id, balance=20, reserved=20, reservations=2, debits=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["commit", "release"])
async def test_concurrent_duplicates_and_terminal_replay(db, credit_fixture, action):
    reservations = await asyncio.wait_for(
        asyncio.gather(*(_reserve_credit(db, credit_fixture) for _ in range(5))), 15
    )
    assert all(r == reservations[0] for r in reservations)
    info = reservations[0]
    await _assert_credit_state(
        db, info.user_id, balance=20, reserved=10, reservations=1, debits=0
    )
    if action == "commit":
        command = _commit_command(info)
        service = CreditService.commit_credit_reservation
    else:
        command = _release_command(info)
        service = CreditService.release_credit_reservation
    finalized = await asyncio.wait_for(
        asyncio.gather(*(_invoke_credit(db, service, command) for _ in range(5))), 15
    )
    assert all(r == finalized[0] for r in finalized)
    assert (
        await _reserve_credit(db, credit_fixture, now=NOW + timedelta(days=1))
        == finalized[0]
    )
    await _assert_credit_state(
        db,
        info.user_id,
        balance=10 if action == "commit" else 20,
        reserved=0,
        reservations=1,
        debits=1 if action == "commit" else 0,
    )
    if action == "commit":
        async with db.begin():
            row = await db.scalar(
                select(CreditTransaction).where(
                    CreditTransaction.reason == "chat_usage"
                )
            )
            assert row.amount == -10 and row.reference_id == command.result_id
            stored = await db.get(CreditReservation, info.id)
            assert stored.transaction_id == row.id and stored.finalized_at is not None
        with pytest.raises(Types.CreditReservationConflictError):
            await _invoke_credit(db, service, replace(command, result_id=uuid4()))
        with pytest.raises(Types.CreditReservationConflictError):
            await _invoke_credit(
                db, CreditService.release_credit_reservation, _release_command(info)
            )
    else:
        with pytest.raises(Types.CreditReservationConflictError):
            await _invoke_credit(
                db, CreditService.commit_credit_reservation, _commit_command(info)
            )


@pytest.mark.asyncio
async def test_commit_release_race_has_only_one_terminal_transition(db, credit_fixture):
    info = await _reserve_credit(db, credit_fixture)
    results = await asyncio.wait_for(
        asyncio.gather(
            _invoke_credit(
                db, CreditService.commit_credit_reservation, _commit_command(info)
            ),
            _invoke_credit(
                db, CreditService.release_credit_reservation, _release_command(info)
            ),
            return_exceptions=True,
        ),
        15,
    )
    assert (
        sum(isinstance(r, Types.CreditReservationConflictError) for r in results) == 1
    )
    success = next(r for r in results if isinstance(r, Types.CreditReservationInfo))
    committed = success.status is Types.CreditReservationStatus.COMMITTED
    await _assert_credit_state(
        db,
        info.user_id,
        balance=10 if committed else 20,
        reserved=0,
        reservations=1,
        debits=int(committed),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("already_reserved", [False, True])
async def test_key_quote_and_execution_conflicts(db, credit_fixture, already_reserved):
    info = await _reserve_credit(db, credit_fixture) if already_reserved else None
    request = credit_fixture.request
    mismatches = [
        replace(request, operation_fingerprint="sha256:" + "b" * 64),
        replace(request, operation_kind=Types.BillingOperationKind.USER_CONTINUATION),
        replace(request, product=None),
        replace(request, product=replace(request.product, product_snapshot_id=uuid4())),
        replace(request, input_tokens=61),
        replace(request, max_output_tokens=31),
        replace(request, execution=replace(request.execution, model_id=uuid4())),
        replace(
            request,
            execution=replace(
                request.execution,
                pricing_settings=(Types.PricingSettingInfo(name="x", value="1"),),
            ),
        ),
    ]
    for changed in mismatches:
        with pytest.raises(Types.BillingQuoteConflictError):
            await _reserve_credit(db, replace(credit_fixture, request=changed))
    if info is None:
        info = await _reserve_credit(db, credit_fixture)
    with pytest.raises(Types.CreditReservationConflictError):
        await _reserve_credit(db, replace(credit_fixture, quote_id=uuid4()))
    other_key = uuid4()
    # A used quote cannot be reused under a new request, even after release.
    await _invoke_credit(
        db, CreditService.release_credit_reservation, _release_command(info)
    )
    with pytest.raises(Types.BillingQuoteConflictError):
        await _reserve_credit(
            db,
            replace(
                credit_fixture,
                request_key=other_key,
                request=replace(request, request_key=other_key),
            ),
        )
    with pytest.raises(Types.CreditReservationConflictError):
        await _reserve_credit(db, replace(credit_fixture, request_key=other_key))
    await _assert_credit_state(
        db, info.user_id, balance=20, reserved=0, reservations=1, debits=0
    )


@pytest.mark.asyncio
async def test_owner_and_reservation_identity_checks(db, credit_fixture):
    other_user = uuid4()
    async with db.begin():
        db.add(User(id=other_user, email=f"{other_user}@credit.test"))
        await db.flush()
        db.add(CreditAccount(user_id=other_user, balance=0))
    with pytest.raises(Types.BillingQuoteNotFoundError):
        await _reserve_credit(
            db,
            replace(
                credit_fixture,
                user_id=other_user,
                request=replace(credit_fixture.request, user_id=other_user),
            ),
        )
    info = await _reserve_credit(db, credit_fixture)
    with pytest.raises(Types.CreditReservationNotFoundError):
        await _invoke_credit(
            db,
            CreditService.release_credit_reservation,
            replace(_release_command(info), user_id=other_user),
        )
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke_credit(
            db,
            CreditService.release_credit_reservation,
            replace(_release_command(info), reservation_id=uuid4()),
        )


@pytest.mark.asyncio
async def test_expired_new_quote_and_live_reservation_replay(db, credit_fixture):
    with pytest.raises(Types.BillingQuoteExpiredError):
        await _reserve_credit(db, credit_fixture, now=NOW + timedelta(seconds=60))
    await _assert_credit_state(
        db, credit_fixture.user_id, balance=20, reserved=0, reservations=0, debits=0
    )
    info = await _reserve_credit(db, credit_fixture, now=NOW + timedelta(seconds=59))
    assert (
        await _reserve_credit(db, credit_fixture, now=NOW + timedelta(days=1)) == info
    )
    # No TTL release: a still-running generation retains its reservation.
    await _assert_credit_state(
        db, info.user_id, balance=20, reserved=10, reservations=1, debits=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reserve", "commit", "release"])
async def test_outer_rollback_preserves_balance_reservation_and_ledger(
    db, credit_fixture, action
):
    info = None if action == "reserve" else await _reserve_credit(db, credit_fixture)
    with pytest.raises(RuntimeError, match="caller failure"):
        async with use_case_transaction(db):
            if action == "reserve":
                await CreditService.reserve_credit(
                    db, credit_fixture, clock=lambda: NOW
                )
            elif action == "commit":
                await CreditService.commit_credit_reservation(db, _commit_command(info))
            else:
                await CreditService.release_credit_reservation(
                    db, _release_command(info)
                )
            raise RuntimeError("caller failure")
    await _assert_credit_state(
        db,
        credit_fixture.user_id,
        balance=20,
        reserved=0 if action == "reserve" else 10,
        reservations=0 if action == "reserve" else 1,
        debits=0,
    )
    if info is not None:
        assert await _reserve_credit(db, credit_fixture) == info


@pytest.mark.asyncio
async def test_ledger_write_failure_rolls_back_even_if_caller_catches(
    db, credit_fixture, monkeypatch
):
    info = await _reserve_credit(db, credit_fixture)
    original = Repository.finalize_credit_reservation

    async def fail_after_ledger(*args, **kwargs):
        raise RuntimeError("injected failure after balance and ledger write")

    monkeypatch.setattr(Repository, "finalize_credit_reservation", fail_after_ledger)
    async with db.begin():
        with pytest.raises(RuntimeError, match="injected failure"):
            await CreditService.commit_credit_reservation(db, _commit_command(info))
    await _assert_credit_state(
        db, info.user_id, balance=20, reserved=10, reservations=1, debits=0
    )
    monkeypatch.setattr(Repository, "finalize_credit_reservation", original)
    await _invoke_credit(
        db, CreditService.commit_credit_reservation, _commit_command(info)
    )
    await _assert_credit_state(
        db, info.user_id, balance=10, reserved=0, reservations=1, debits=1
    )


@pytest.mark.asyncio
async def test_expiry_is_checked_after_waiting_for_account_lock(db, credit_fixture):
    clock_checked = asyncio.Event()
    waiter_pid = asyncio.Future()
    now = NOW

    def clock():
        clock_checked.set()
        return now

    async def waiter():
        async with AsyncSession(db.bind) as session:
            async with session.begin():
                waiter_pid.set_result(
                    await session.scalar(text("SELECT pg_backend_pid()"))
                )
                return await CreditService.reserve_credit(
                    session, credit_fixture, clock=clock
                )

    async with db.begin():
        await db.scalar(select(CreditAccount).with_for_update())
        task = asyncio.create_task(waiter())
        pid = await asyncio.wait_for(waiter_pid, 5)
        try:

            async def wait_until_blocked():
                async with AsyncSession(db.bind) as monitor:
                    while True:
                        blocked = await monitor.scalar(
                            text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"),
                            {"pid": pid},
                        )
                        if blocked:
                            return
                        await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_until_blocked(), 5)
            assert not clock_checked.is_set()
            now = NOW + timedelta(seconds=60)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
    with pytest.raises(Types.BillingQuoteExpiredError):
        await asyncio.wait_for(task, 5)
    await _assert_credit_state(
        db, credit_fixture.user_id, balance=20, reserved=0, reservations=0, debits=0
    )


@pytest.mark.asyncio
async def test_explicit_transaction_and_missing_account(db, credit_fixture):
    with pytest.raises(RuntimeError, match="explicit caller-owned"):
        await CreditService.reserve_credit(db, credit_fixture, clock=lambda: NOW)
    await db.execute(text("SELECT 1"))
    with pytest.raises(RuntimeError, match="explicit caller-owned"):
        await CreditService.reserve_credit(db, credit_fixture, clock=lambda: NOW)
    await db.rollback()
    with pytest.raises(Types.CreditAccountNotFoundError):
        await CreditService.get_credit_balance(
            db, Types.GetCreditBalanceCommand(user_id=uuid4())
        )
    await db.rollback()
