"""Credit alone needs no quote, model, tokens or billing request."""

import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.models.credit import CreditBalance, CreditReservation, CreditTransaction
from app.db.models.identity import User
from app.modules.commerce.billing import repository as BillingRepository
from app.modules.commerce.billing.service import credits as BillingCreditService
from app.modules.commerce.credit import repository as Repository
from app.modules.commerce.credit import types as Types
from app.modules.commerce.credit.service import command as CommandService
from app.modules.commerce.credit.service import query as QueryService
from credit_support import fund_credit
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_billing_credits import (  # noqa: F401
    NOW,
    _assert_credit_state,
    _credit_fixture,
)
from test_billing_prices import _configuration, _request_info  # noqa: F401


@pytest_asyncio.fixture
async def credit_command(db):
    uid = uuid4()
    async with db.begin():
        db.add(User(id=uid, email=f"{uid}@independent-credit.test"))
        await db.flush()
        await fund_credit(db, uid)
    return Types.ReserveCreditCommand(
        currency_code="CREDIT",
        user_id=uid,
        namespace="standalone",
        request_key=uuid4(),
        amount=10,
        reference_id=uuid4(),
        reason="document_export",
        settlement_key=str(uuid4()),
        created_at=datetime.now(UTC),
    )


async def _invoke(db, service, command):
    async with AsyncSession(db.bind, expire_on_commit=False) as session:
        async with session.begin():
            return await service(session, command)


def _commit(info):
    return Types.CommitCreditReservationCommand(
        currency_code="CREDIT",
        user_id=info.user_id,
        namespace=info.namespace,
        request_key=info.request_key,
        reservation_id=info.id,
        result_id=uuid4(),
    )


def _release(info):
    return Types.ReleaseCreditReservationCommand(
        currency_code="CREDIT",
        user_id=info.user_id,
        namespace=info.namespace,
        request_key=info.request_key,
        reservation_id=info.id,
    )


@pytest.mark.asyncio
async def test_independent_lifecycle_opaque_metadata_and_terminal_retries(
    db, credit_command
):
    with pytest.raises(FrozenInstanceError):
        credit_command.amount = 5
    reserved = await _invoke(db, CommandService.reserve_credit, credit_command)
    assert reserved.reference_id == credit_command.reference_id
    assert (
        await QueryService.get_credit_reservation(
            db,
            Types.GetCreditReservationCommand(
                currency_code="CREDIT",
                user_id=reserved.user_id,
                namespace=reserved.namespace,
                request_key=reserved.request_key,
            ),
        )
        == reserved
    )
    await db.rollback()
    command = _commit(reserved)
    results = await asyncio.gather(
        *[
            _invoke(db, CommandService.commit_credit_reservation, command)
            for _ in range(5)
        ]
    )
    assert all(info == results[0] for info in results)
    assert results[0].status is Types.CreditReservationStatus.COMMITTED
    assert (
        await _invoke(
            db,
            CommandService.reserve_credit,
            replace(
                credit_command, created_at=credit_command.created_at + timedelta(days=1)
            ),
        )
        == results[0]
    )
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(
            db,
            CommandService.commit_credit_reservation,
            replace(command, result_id=uuid4()),
        )
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(db, CommandService.release_credit_reservation, _release(reserved))
    ledger = (
        await db.scalars(
            select(CreditTransaction).where(CreditTransaction.operation == "consume")
        )
    ).one()
    assert (
        ledger.amount,
        ledger.reason,
        ledger.reference_id,
        ledger.idempotency_key,
    ) == (
        -10,
        credit_command.reason,
        command.result_id,
        credit_command.settlement_key,
    )
    assert await QueryService.get_credit_balance(
        db,
        Types.GetCreditBalanceCommand(currency_code="CREDIT", user_id=reserved.user_id),
    ) == Types.CreditBalanceInfo(
        currency_code="CREDIT",
        user_id=reserved.user_id,
        balance_credit=10,
        reserved_credit=0,
        available_credit=10,
        free=Types.CreditBucketInfo(
            balance_credit=10, reserved_credit=0, available_credit=10
        ),
        paid=Types.CreditBucketInfo(
            balance_credit=0, reserved_credit=0, available_credit=0
        ),
    )


@pytest.mark.asyncio
async def test_namespace_isolation_and_release_retains_original_amount(
    db, credit_command
):
    first = await _invoke(db, CommandService.reserve_credit, credit_command)
    second_command = replace(
        credit_command, namespace="another", settlement_key=str(uuid4())
    )
    second = await _invoke(db, CommandService.reserve_credit, second_command)
    assert first.id != second.id
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(
            db,
            CommandService.release_credit_reservation,
            replace(_release(first), namespace="another"),
        )
    results = await asyncio.gather(
        *[
            _invoke(db, CommandService.release_credit_reservation, _release(first))
            for _ in range(5)
        ]
    )
    assert all(info == results[0] for info in results)
    assert results[0].reserved_credit == 10
    assert (
        await _invoke(db, CommandService.reserve_credit, credit_command) == results[0]
    )
    assert (
        await db.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.operation == "consume")
        )
        == 0
    )
    balance = await QueryService.get_credit_balance(
        db, Types.GetCreditBalanceCommand(currency_code="CREDIT", user_id=first.user_id)
    )
    assert (balance.balance_credit, balance.reserved_credit) == (20, 10)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", -1),
        ("amount", True),
        ("amount", 2**63),
        ("amount", 1.5),
        ("namespace", ""),
        ("reason", " "),
        ("settlement_key", " bad "),
        ("reference_id", "not-uuid"),
        ("created_at", datetime(2026, 1, 1)),
    ],
)
async def test_invalid_commands_have_no_writes(db, credit_command, field, value):
    with pytest.raises(Types.InvalidCreditCommandError):
        await _invoke(
            db, CommandService.reserve_credit, replace(credit_command, **{field: value})
        )
    assert await db.scalar(select(func.count()).select_from(CreditReservation)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 9),
        ("reference_id", uuid4()),
        ("reason", "another"),
        ("settlement_key", "another"),
    ],
)
async def test_changed_reservation_terms_conflict(db, credit_command, field, value):
    await _invoke(db, CommandService.reserve_credit, credit_command)
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(
            db, CommandService.reserve_credit, replace(credit_command, **{field: value})
        )


@pytest.mark.asyncio
async def test_settlement_key_is_scoped_to_user(db, credit_command):
    other = uuid4()
    async with db.begin():
        db.add(User(id=other, email=f"{other}@credit.test"))
        await db.flush()
        await fund_credit(db, other)
    outcomes = await asyncio.gather(
        _invoke(db, CommandService.reserve_credit, credit_command),
        _invoke(
            db, CommandService.reserve_credit, replace(credit_command, user_id=other)
        ),
        return_exceptions=True,
    )
    assert all(isinstance(value, Types.CreditReservationInfo) for value in outcomes)
    assert await db.scalar(select(func.sum(CreditBalance.reserved_credit))) == 20
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(
            db,
            CommandService.reserve_credit,
            replace(credit_command, request_key=uuid4()),
        )


@pytest.mark.asyncio
async def test_zero_amount_and_existing_ledger_key(db, credit_command):
    async with db.begin():
        db.add(
            CreditTransaction(
                user_id=credit_command.user_id,
                amount=0,
                reason="legacy",
                currency_code="CREDIT",
                namespace=credit_command.namespace,
                request_key=uuid4(),
                operation="consume",
                idempotency_key="taken",
            )
        )
    with pytest.raises(Types.CreditReservationConflictError):
        await _invoke(
            db,
            CommandService.reserve_credit,
            replace(credit_command, settlement_key="taken"),
        )
    info = await _invoke(
        db, CommandService.reserve_credit, replace(credit_command, amount=0)
    )
    committed = await _invoke(
        db, CommandService.commit_credit_reservation, _commit(info)
    )
    assert (
        await db.scalar(
            select(CreditTransaction.amount).where(
                CreditTransaction.id == committed.transaction_id
            )
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reserve", "commit", "release"])
async def test_credit_standalone_outer_rollback(db, credit_command, action):
    info = (
        None
        if action == "reserve"
        else await _invoke(db, CommandService.reserve_credit, credit_command)
    )
    with pytest.raises(RuntimeError, match="caller failure"):
        async with db.begin():
            if action == "reserve":
                await CommandService.reserve_credit(db, credit_command)
            elif action == "commit":
                await CommandService.commit_credit_reservation(db, _commit(info))
            else:
                await CommandService.release_credit_reservation(db, _release(info))
            raise RuntimeError("caller failure")
    balance = await QueryService.get_credit_balance(
        db,
        Types.GetCreditBalanceCommand(
            currency_code="CREDIT", user_id=credit_command.user_id
        ),
    )
    assert balance.balance_credit == 20
    assert balance.reserved_credit == (0 if action == "reserve" else 10)
    assert (
        await db.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.operation == "consume")
        )
        == 0
    )


@pytest.mark.asyncio
async def test_standalone_transaction_requirement_and_missing_account(
    db, credit_command
):
    with pytest.raises(RuntimeError, match="explicit caller-owned"):
        await CommandService.reserve_credit(db, credit_command)
    await db.execute(text("SELECT 1"))
    with pytest.raises(RuntimeError, match="explicit caller-owned"):
        await CommandService.lock_credit_account(
            db,
            Types.LockCreditAccountCommand(
                currency_code="CREDIT", user_id=credit_command.user_id
            ),
        )
    await db.rollback()
    with pytest.raises(Types.CreditAccountNotFoundError):
        await _invoke(
            db, CommandService.reserve_credit, replace(credit_command, user_id=uuid4())
        )


@pytest.mark.asyncio
async def test_binding_insert_failure_rolls_back_credit_even_when_caught(
    db, credit_fixture, monkeypatch
):
    async def fail_binding(*args, **kwargs):
        raise RuntimeError("binding insert failed")

    monkeypatch.setattr(BillingRepository, "create_credit_binding", fail_binding)
    async with db.begin():
        with pytest.raises(RuntimeError, match="binding insert failed"):
            await BillingCreditService.reserve_credit(
                db, credit_fixture, clock=lambda: NOW
            )
    await _assert_credit_state(
        db, credit_fixture.user_id, balance=20, reserved=0, reservations=0, debits=0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,target",
    [
        ("reserve", "create_credit_reservation"),
        ("release", "finalize_credit_reservation"),
    ],
)
async def test_credit_savepoint_failure_is_atomic(
    db, credit_command, monkeypatch, action, target
):
    info = (
        None
        if action == "reserve"
        else await _invoke(db, CommandService.reserve_credit, credit_command)
    )

    async def fail(*args, **kwargs):
        raise RuntimeError("injected persistence failure")

    monkeypatch.setattr(Repository, target, fail)
    async with db.begin():
        with pytest.raises(RuntimeError, match="injected persistence failure"):
            if action == "reserve":
                await CommandService.reserve_credit(db, credit_command)
            else:
                await CommandService.release_credit_reservation(db, _release(info))
    balance = await QueryService.get_credit_balance(
        db,
        Types.GetCreditBalanceCommand(
            currency_code="CREDIT", user_id=credit_command.user_id
        ),
    )
    assert (balance.balance_credit, balance.reserved_credit) == (
        20,
        0 if action == "reserve" else 10,
    )
