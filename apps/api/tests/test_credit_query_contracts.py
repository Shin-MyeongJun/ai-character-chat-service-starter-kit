"""Offline credit history SQL and mapping; PostgreSQL locks/constraints need DB tests."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.credit import (
    CreditReservation,
    CreditTransaction,
    CreditTransactionEntry,
)
from app.modules.commerce.credit import types as Types
from app.modules.commerce.credit.mapper import persistence as PersistenceMapper
from app.modules.commerce.credit.service import query as QueryService

STAMP = datetime(2026, 10, 20, tzinfo=UTC)


def _sqlite_cursor(cursor: Types.CreditCursor) -> Types.CreditCursor:
    # SQLite drops timezone metadata; all fixture timestamps were stored in UTC.
    return replace(cursor, created_at=cursor.created_at.replace(tzinfo=UTC))


@pytest.fixture
def history_database() -> Iterator[tuple[Session, AsyncMock]]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Copy only columns: PostgreSQL CHECKs, FKs and locks are outside this read test.
    for model in (CreditTransaction, CreditTransactionEntry, CreditReservation):
        Table(
            model.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    # SQLite's UUID name has numeric affinity; store UUIDs as text.
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                )
                for column in model.__table__.columns
            ),
        )
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.scalars.side_effect = sync_session.scalars
            yield sync_session, session
    finally:
        engine.dispose()


def _transaction(
    user_id: UUID,
    transaction_id: int,
    amount: int,
    *,
    currency_code: str | None = "CREDIT",
    namespace: str = "export",
    reason: str = "document",
    created_at: datetime = STAMP,
) -> CreditTransaction:
    return CreditTransaction(
        id=UUID(int=transaction_id),
        user_id=user_id,
        currency_code=currency_code,
        namespace=namespace if currency_code else None,
        request_key=uuid4() if currency_code else None,
        operation="legacy"
        if currency_code is None
        else "grant"
        if amount > 0
        else "consume",
        amount=amount,
        reason=reason,
        reference_id=None,
        idempotency_key=str(uuid4()),
        created_at=created_at,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("direction", "expected_amounts"),
    [(None, [-2, 0, -7, 10]), ("usage", [-2, -7]), ("acquisition", [10])],
)
async def test_transaction_filters_allocations_and_tied_cursor(
    history_database: tuple[Session, AsyncMock],
    direction: str | None,
    expected_amounts: list[int],
) -> None:
    sync_session, session = history_database
    user_id = uuid4()
    sync_session.add_all(
        [
            *(
                _transaction(user_id, i, amount)
                for i, amount in enumerate([10, -7, 0, -2], 1)
            ),
            _transaction(uuid4(), 5, -50),
            _transaction(user_id, 6, -60, currency_code="GEM"),
            _transaction(user_id, 7, -70, currency_code=None),
            _transaction(user_id, 8, -80, namespace="other"),
            _transaction(user_id, 9, -90, reason="other"),
            _transaction(user_id, 10, -100, created_at=STAMP - timedelta(days=1)),
            _transaction(user_id, 11, -110, created_at=STAMP + timedelta(days=1)),
            CreditTransactionEntry(
                transaction_id=UUID(int=4),
                user_id=user_id,
                currency_code="CREDIT",
                bucket="free",
                amount=-1,
            ),
            CreditTransactionEntry(
                transaction_id=UUID(int=4),
                user_id=user_id,
                currency_code="CREDIT",
                bucket="paid",
                amount=-1,
            ),
        ]
    )
    sync_session.flush()
    command = Types.ListCreditTransactionsCommand(
        user_id=user_id,
        currency_code="CREDIT",
        namespace="export",
        reason="document",
        start=STAMP,
        end=STAMP + timedelta(days=1),
        limit=1,
        direction=direction,
    )
    items: list[Types.CreditTransactionInfo] = []
    for _ in range(5):
        page = await QueryService.list_credit_transactions(session, command)
        items.extend(page.items)
        if page.next_cursor is None:
            break
        assert page.next_cursor == Types.CreditCursor(
            created_at=page.items[-1].created_at,
            id=page.items[-1].id,
        )
        command = replace(command, cursor=_sqlite_cursor(page.next_cursor))
    else:
        pytest.fail("History cursor did not terminate.")
    assert [item.amount for item in items] == expected_amounts
    if direction != "acquisition":
        assert (items[0].free_amount, items[0].paid_amount) == (-1, -1)
    zero = next((item for item in items if item.amount == 0), None)
    if direction is None:
        assert zero is not None
        assert (zero.free_amount, zero.paid_amount) == (0, 0)


@pytest.mark.asyncio
async def test_legacy_transactions_preserve_unknown_allocation(
    history_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = history_database
    user_id = uuid4()
    sync_session.add_all(
        [
            _transaction(user_id, 1, -7, currency_code=None),
            _transaction(uuid4(), 2, -9, currency_code=None),
            _transaction(user_id, 3, 10),
        ]
    )
    sync_session.flush()
    page = await QueryService.list_credit_transactions(
        session,
        Types.ListCreditTransactionsCommand(user_id=user_id, currency_code=None),
    )
    assert len(page.items) == 1 and page.next_cursor is None
    item = page.items[0]
    assert item.amount == -7 and item.currency_code is None
    assert (item.free_amount, item.paid_amount) == (None, None)
    assert PersistenceMapper.credit_transaction_row_to_info(None) is None


@pytest.mark.asyncio
async def test_reservation_owner_currency_status_cursor_and_legacy(
    history_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = history_database
    user_id = uuid4()
    for i, owner, currency, status in [
        (1, user_id, "CREDIT", "reserved"),
        (2, user_id, "CREDIT", "reserved"),
        (3, user_id, "CREDIT", "released"),
        (4, uuid4(), "CREDIT", "reserved"),
        (5, user_id, "GEM", "reserved"),
        (6, user_id, None, "reserved"),
    ]:
        sync_session.add(
            CreditReservation(
                id=UUID(int=i),
                user_id=owner,
                currency_code=currency,
                namespace="export",
                request_key=uuid4(),
                reference_id=uuid4(),
                reason="document",
                settlement_key=str(uuid4()),
                reserved_credit=7,
                status=status,
                result_id=None,
                transaction_id=None,
                created_at=STAMP,
                finalized_at=STAMP if status == "released" else None,
                free_amount=3 if currency else None,
                paid_amount=4 if currency else None,
                allocation_status="allocated" if currency else "legacy_unknown",
            )
        )
    sync_session.flush()
    command = Types.ListCreditReservationsCommand(
        user_id=user_id,
        currency_code="CREDIT",
        namespace="export",
        reason="document",
        start=STAMP,
        end=STAMP + timedelta(days=1),
        limit=1,
        status=Types.CreditReservationStatus.RESERVED,
    )
    first = await QueryService.list_credit_reservations(session, command)
    assert first.next_cursor is not None
    second = await QueryService.list_credit_reservations(
        session,
        replace(command, cursor=_sqlite_cursor(first.next_cursor)),
    )
    assert first.next_cursor is not None and second.next_cursor is None
    assert [first.items[0].id, second.items[0].id] == [UUID(int=2), UUID(int=1)]
    assert (first.items[0].free_amount, first.items[0].paid_amount) == (3, 4)
    lookup = Types.GetCreditReservationCommand(
        user_id=user_id,
        currency_code="CREDIT",
        namespace="export",
        request_key=first.items[0].request_key,
    )
    assert await QueryService.get_credit_reservation(session, lookup) == first.items[0]
    assert (
        await QueryService.get_credit_reservation(
            session, replace(lookup, user_id=uuid4())
        )
        is None
    )
    legacy = await QueryService.list_credit_reservations(
        session,
        replace(command, currency_code=None),
    )
    assert len(legacy.items) == 1 and legacy.next_cursor is None
    assert legacy.items[0].allocation_status == "legacy_unknown"
    assert (legacy.items[0].free_amount, legacy.items[0].paid_amount) == (None, None)
    assert PersistenceMapper.credit_reservation_entity_to_info(None) is None
