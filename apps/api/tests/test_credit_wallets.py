"""Real PostgreSQL classified wallets: allocation, concurrency, audit, atomicity."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.db.models.credit import (
    CreditAccount,
    CreditBalance,
    CreditReservation,
    CreditTransaction,
    CreditTransactionEntry,
    CreditWallet,
)
from app.db.models.identity import User
from app.modules.commerce.credit import repository as Repository
from app.modules.commerce.credit import types as Types
from app.modules.commerce.credit.service import command as Commands
from app.modules.commerce.credit.service import query as Queries
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def invoke(db, service, command):
    async with AsyncSession(db.bind, expire_on_commit=False) as session:
        async with session.begin():
            return await service(session, command)


async def user(db):
    uid = uuid4()
    async with db.begin():
        db.add(User(id=uid, email=f"{uid}@wallet.test"))
    return uid


def grant(uid, amount=30, bucket=Types.CreditBucket.FREE, currency="CREDIT"):
    return Types.GrantCreditCommand(
        user_id=uid,
        currency_code=currency,
        bucket=bucket,
        amount=amount,
        namespace="test",
        reason="award",
        request_key=uuid4(),
        reference_id=uuid4(),
    )


def reserve(uid, amount=50, currency="CREDIT"):
    return Types.ReserveCreditCommand(
        user_id=uid,
        currency_code=currency,
        amount=amount,
        namespace="test",
        reason="export",
        request_key=uuid4(),
        reference_id=uuid4(),
        settlement_key=str(uuid4()),
        created_at=datetime.now(UTC),
    )


def finalize(info, commit=True):
    values = dict(
        user_id=info.user_id,
        currency_code=info.currency_code,
        namespace=info.namespace,
        request_key=info.request_key,
        reservation_id=info.id,
    )
    if commit:
        return Types.CommitCreditReservationCommand(**values, result_id=uuid4())
    return Types.ReleaseCreditReservationCommand(**values)


async def balance(db, uid, currency="CREDIT"):
    return await invoke(
        db,
        Queries.get_credit_balance,
        Types.GetCreditBalanceCommand(user_id=uid, currency_code=currency),
    )


async def reconcile(db, uid, currency="CREDIT"):
    info = await balance(db, uid, currency)
    async with AsyncSession(db.bind) as session:
        for bucket in ("free", "paid"):
            part = getattr(info, bucket)
            ledger = await session.scalar(
                select(func.coalesce(func.sum(CreditTransactionEntry.amount), 0)).where(
                    CreditTransactionEntry.user_id == uid,
                    CreditTransactionEntry.currency_code == currency,
                    CreditTransactionEntry.bucket == bucket,
                )
            )
            held = await session.scalar(
                select(
                    func.coalesce(
                        func.sum(getattr(CreditReservation, bucket + "_amount")), 0
                    )
                ).where(
                    CreditReservation.user_id == uid,
                    CreditReservation.currency_code == currency,
                    CreditReservation.status == "reserved",
                )
            )
            assert part.balance_credit == ledger
            assert part.reserved_credit == held
            assert part.available_credit == ledger - held >= 0
        transactions = (
            await session.execute(
                select(CreditTransaction.id, CreditTransaction.amount).where(
                    CreditTransaction.user_id == uid,
                    CreditTransaction.currency_code == currency,
                )
            )
        ).all()
        for tid, amount in transactions:
            assert amount == await session.scalar(
                select(func.coalesce(func.sum(CreditTransactionEntry.amount), 0)).where(
                    CreditTransactionEntry.transaction_id == tid
                )
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "free,paid,amount,allocation",
    [
        (30, 0, 20, (20, 0)),
        (0, 70, 50, (0, 50)),
        (30, 70, 50, (30, 20)),
        (0, 0, 0, (0, 0)),
    ],
)
@pytest.mark.parametrize("commit", [True, False])
async def test_bucket_lifecycle_and_fixed_allocation(
    db, free, paid, amount, allocation, commit
):
    uid = await user(db)
    await invoke(
        db,
        Commands.prepare_credit_wallet,
        Types.PrepareCreditWalletCommand(user_id=uid, currency_code="CREDIT"),
    )
    for bucket, value in (
        (Types.CreditBucket.FREE, free),
        (Types.CreditBucket.PAID, paid),
    ):
        if value:
            await invoke(db, Commands.grant_credit, grant(uid, value, bucket))
    request = reserve(uid, amount)
    info = await invoke(db, Commands.reserve_credit, request)
    assert (info.free_amount, info.paid_amount) == allocation
    await reconcile(db, uid)
    await invoke(db, Commands.grant_credit, grant(uid, 11))
    assert await invoke(db, Commands.reserve_credit, request) == info
    command = finalize(info, commit)
    service = (
        Commands.commit_credit_reservation
        if commit
        else Commands.release_credit_reservation
    )
    results = await asyncio.wait_for(
        asyncio.gather(*(invoke(db, service, command) for _ in range(4))), 10
    )
    assert all(result == results[0] for result in results)
    after = await balance(db, uid)
    assert (after.free.balance_credit, after.paid.balance_credit) == (
        free + 11 - (allocation[0] if commit else 0),
        paid - (allocation[1] if commit else 0),
    )
    assert after.reserved_credit == 0
    await reconcile(db, uid)
    async with AsyncSession(db.bind) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(CreditTransaction)
            .where(CreditTransaction.operation == "consume")
        )
        assert count == int(commit)


@pytest.mark.asyncio
async def test_concurrent_first_grants_keys_and_preparation(db):
    uid = await user(db)
    command = grant(uid)
    requests = [command] * 5 + [replace(command, request_key=uuid4()) for _ in range(3)]
    gate = asyncio.Barrier(len(requests))

    async def run(item):
        await gate.wait()
        return await invoke(db, Commands.grant_credit, item)

    results = await asyncio.wait_for(
        asyncio.gather(*(run(item) for item in requests)), 15
    )
    assert all(result == results[0] for result in results[:5])
    assert len({result.id for result in results}) == 4
    assert (await balance(db, uid)).balance_credit == 120
    await reconcile(db, uid)
    prepared = await asyncio.gather(
        *(
            invoke(
                db,
                Commands.prepare_credit_wallet,
                Types.PrepareCreditWalletCommand(user_id=uid, currency_code="SECOND"),
            )
            for _ in range(4)
        )
    )
    assert all(info == prepared[0] for info in prepared)
    async with AsyncSession(db.bind) as session:
        assert await session.scalar(select(func.count()).select_from(CreditWallet)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(CreditBalance)) == 4
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", 31),
        ("bucket", Types.CreditBucket.PAID),
        ("reason", "changed"),
        ("reference_id", uuid4()),
    ],
)
async def test_grant_reuse_conflicts(db, field, value):
    uid = await user(db)
    command = grant(uid)
    result = await invoke(db, Commands.grant_credit, command)
    assert await invoke(db, Commands.grant_credit, command) == result
    with pytest.raises(Types.CreditGrantConflictError):
        await invoke(db, Commands.grant_credit, replace(command, **{field: value}))
    await reconcile(db, uid)


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [True, False, 0, -1, 2**63, 1.5, "10"])
async def test_invalid_grants_do_not_create_wallet(db, amount):
    uid = await user(db)
    with pytest.raises(Types.InvalidCreditCommandError):
        await invoke(db, Commands.grant_credit, grant(uid, amount))
    async with AsyncSession(db.bind) as session:
        assert await session.scalar(select(func.count()).select_from(CreditWallet)) == 0


@pytest.mark.asyncio
async def test_grant_overflow_is_atomic_and_retry_at_capacity(db):
    uid = await user(db)
    command = grant(uid, 2**63 - 1)
    first = await invoke(db, Commands.grant_credit, command)
    assert await invoke(db, Commands.grant_credit, command) == first
    with pytest.raises(Types.InvalidCreditCommandError):
        await invoke(db, Commands.grant_credit, grant(uid, 1, Types.CreditBucket.PAID))
    assert (await balance(db, uid)).balance_credit == 2**63 - 1
    await reconcile(db, uid)


@pytest.mark.asyncio
async def test_currency_user_namespace_isolation_and_no_substitution(db):
    uid, other = await user(db), await user(db)
    command = grant(uid, 30)
    for item in (
        command,
        replace(command, currency_code="GEM"),
        replace(command, user_id=other),
        replace(command, namespace="other"),
    ):
        await invoke(db, Commands.grant_credit, item)
    with pytest.raises(Types.InsufficientCreditError):
        await invoke(db, Commands.reserve_credit, reserve(uid, 61))
    request = reserve(uid, 20)
    one = await invoke(db, Commands.reserve_credit, request)
    two = await invoke(
        db, Commands.reserve_credit, replace(request, currency_code="GEM")
    )
    three = await invoke(
        db, Commands.reserve_credit, replace(request, namespace="other")
    )
    assert len({one.id, two.id, three.id}) == 3
    with pytest.raises(Types.CreditReservationNotFoundError):
        await invoke(
            db,
            Commands.commit_credit_reservation,
            replace(finalize(one), user_id=other),
        )
    with pytest.raises(Types.CreditReservationConflictError):
        await invoke(
            db,
            Commands.commit_credit_reservation,
            replace(finalize(one), currency_code="GEM"),
        )
    for currency in ("CREDIT", "GEM"):
        await reconcile(db, uid, currency)


@pytest.mark.asyncio
async def test_concurrent_mixed_reservations_and_commit_release_race(db):
    uid = await user(db)
    await invoke(db, Commands.grant_credit, grant(uid, 30))
    await invoke(db, Commands.grant_credit, grant(uid, 70, Types.CreditBucket.PAID))
    gate = asyncio.Barrier(8)

    async def run():
        await gate.wait()
        return await invoke(db, Commands.reserve_credit, reserve(uid, 25))

    outcomes = await asyncio.wait_for(
        asyncio.gather(*(run() for _ in range(8)), return_exceptions=True), 15
    )
    winners = [r for r in outcomes if isinstance(r, Types.CreditReservationInfo)]
    assert len(winners) == 4
    assert sum(isinstance(r, Types.InsufficientCreditError) for r in outcomes) == 4
    assert sum(r.free_amount for r in winners) == 30
    assert sum(r.paid_amount for r in winners) == 70
    await reconcile(db, uid)
    info = winners[0]
    results = await asyncio.wait_for(
        asyncio.gather(
            invoke(db, Commands.commit_credit_reservation, finalize(info)),
            invoke(db, Commands.release_credit_reservation, finalize(info, False)),
            return_exceptions=True,
        ),
        10,
    )
    assert sum(isinstance(r, Types.CreditReservationInfo) for r in results) == 1
    assert (
        sum(isinstance(r, Types.CreditReservationConflictError) for r in results) == 1
    )
    await reconcile(db, uid)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["outer", "ledger", "entry"])
async def test_first_grant_failure_rolls_back_wallet_balances_and_ledger(
    db, monkeypatch, failure
):
    uid = await user(db)
    command = grant(uid)
    if failure == "ledger":
        original = Repository.create_credit_movement

        async def failing(*args, **kwargs):
            await original(*args, **kwargs)
            raise RuntimeError("grant failure")

        monkeypatch.setattr(Repository, "create_credit_movement", failing)
    if failure == "entry":
        # Genuine DB constraint failure after header + balance writes.
        async with db.begin():
            await db.execute(
                text(
                    "ALTER TABLE credit_transaction_entries ADD CONSTRAINT injected "
                    "CHECK (amount < 0)"
                )
            )
    if failure == "outer":
        with pytest.raises(RuntimeError, match="grant failure"):
            async with db.begin():
                await Commands.grant_credit(db, command)
                raise RuntimeError("grant failure")
    else:
        async with db.begin():
            with pytest.raises((RuntimeError, IntegrityError)):
                await Commands.grant_credit(db, command)
    async with AsyncSession(db.bind) as session:
        for model in (
            CreditWallet,
            CreditBalance,
            CreditTransaction,
            CreditTransactionEntry,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_history_filters_tied_time_cursor_and_unclassified_history(db):
    uid, other = await user(db), await user(db)
    for _ in range(5):
        await invoke(db, Commands.grant_credit, grant(uid))
    await invoke(db, Commands.grant_credit, grant(uid, currency="GEM"))
    await invoke(db, Commands.grant_credit, grant(other))
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    async with db.begin():
        await db.execute(update(CreditTransaction).values(created_at=instant))
    command = Types.ListCreditTransactionsCommand(
        user_id=uid,
        currency_code="CREDIT",
        reason="award",
        namespace="test",
        start=instant,
        end=instant + timedelta(seconds=1),
        limit=2,
    )
    seen = []
    while True:
        page = await invoke(db, Queries.list_credit_transactions, command)
        seen.extend(page.items)
        if page.next_cursor is None:
            break
        command = replace(command, cursor=page.next_cursor)
    assert len(seen) == len({r.id for r in seen}) == 5
    assert [r.id for r in seen] == sorted([r.id for r in seen], reverse=True)
    assert all((r.free_amount, r.paid_amount) == (30, 0) for r in seen)
    requests = [reserve(uid, 10) for _ in range(3)]
    reservations = [await invoke(db, Commands.reserve_credit, r) for r in requests]
    await invoke(
        db, Commands.release_credit_reservation, finalize(reservations[0], False)
    )
    query = Types.ListCreditReservationsCommand(
        user_id=uid,
        currency_code="CREDIT",
        status=Types.CreditReservationStatus.RESERVED,
        reason="export",
        limit=1,
    )
    page = await invoke(db, Queries.list_credit_reservations, query)
    second = await invoke(
        db, Queries.list_credit_reservations, replace(query, cursor=page.next_cursor)
    )
    assert (
        len(page.items) == len(second.items) == 1
        and page.items[0].id != second.items[0].id
    )
    assert second.next_cursor is None
    legacy = await user(db)
    async with db.begin():
        db.add(CreditAccount(user_id=legacy, balance=99))
        db.add(
            CreditTransaction(
                user_id=legacy, amount=99, reason="purchase", idempotency_key="old"
            )
        )
    with pytest.raises(Types.CreditClassificationRequiredError):
        await invoke(db, Commands.grant_credit, grant(legacy))
    history = await invoke(
        db,
        Queries.list_credit_transactions,
        Types.ListCreditTransactionsCommand(user_id=legacy, currency_code=None),
    )
    assert len(history.items) == 1 and history.items[0].free_amount is None
    assert history.items[0].paid_amount is None and history.items[0].amount == 99
    with pytest.raises(Types.CreditClassificationRequiredError):
        await balance(db, legacy)


@pytest.mark.asyncio
async def test_reads_reserve_missing_wallet_do_not_create_or_repair(db):
    uid = await user(db)
    for service, command in (
        (
            Queries.get_credit_balance,
            Types.GetCreditBalanceCommand(user_id=uid, currency_code="CREDIT"),
        ),
        (Commands.reserve_credit, reserve(uid, 0)),
    ):
        with pytest.raises(Types.CreditAccountNotFoundError):
            await invoke(db, service, command)
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(CreditWallet)) == 0
        db.add(CreditWallet(user_id=uid, currency_code="CREDIT"))
    with pytest.raises(ValueError, match="Incomplete"):
        await invoke(
            db,
            Commands.prepare_credit_wallet,
            Types.PrepareCreditWalletCommand(user_id=uid, currency_code="CREDIT"),
        )
    async with AsyncSession(db.bind) as session:
        assert (
            await session.scalar(select(func.count()).select_from(CreditBalance)) == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE credit_balances SET reserved_credit=balance+1",
        "UPDATE credit_balances SET balance=-1",
        "UPDATE credit_reservations SET free_amount=free_amount+1",
        "UPDATE credit_reservations SET status='committed'",
        "UPDATE credit_transactions SET amount=-1 WHERE operation='grant'",
        "UPDATE credit_transaction_entries SET currency_code='MISSING'",
    ],
)
async def test_database_constraints_reject_invalid_state(db, sql):
    uid = await user(db)
    await invoke(db, Commands.grant_credit, grant(uid))
    await invoke(db, Commands.reserve_credit, reserve(uid, 10))
    async with db.begin():
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                await db.execute(text(sql))
    await reconcile(db, uid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"currency_code": "credit"},
        {"currency_code": ""},
        {"currency_code": "A" * 33},
        {"bucket": "free"},
        {"namespace": " bad "},
        {"reason": ""},
        {"reference_id": "invalid"},
    ],
)
async def test_invalid_grant_identity_and_metadata(db, changes):
    uid = await user(db)
    with pytest.raises(Types.InvalidCreditCommandError):
        await invoke(db, Commands.grant_credit, replace(grant(uid), **changes))
    async with AsyncSession(db.bind) as session:
        assert await session.scalar(select(func.count()).select_from(CreditWallet)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"start": datetime(2026, 1, 1)},
        {"cursor": "invalid"},
        {
            "start": datetime(2026, 1, 2, tzinfo=UTC),
            "end": datetime(2026, 1, 1, tzinfo=UTC),
        },
    ],
)
async def test_invalid_history_filters(db, changes):
    uid = await user(db)
    query = Types.ListCreditTransactionsCommand(user_id=uid, currency_code="CREDIT")
    with pytest.raises(Types.InvalidCreditCommandError):
        await invoke(db, Queries.list_credit_transactions, replace(query, **changes))
