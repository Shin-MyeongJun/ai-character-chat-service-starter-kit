"""Offline billing value/SQL contracts; PostgreSQL locks and constraints need DB tests."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.billing import Payment, UsageLog
from app.db.models.product_usage import ProductPaymentEvent
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import persistence as PersistenceMapper

STAMP = datetime(2026, 10, 20, tzinfo=UTC)


@pytest.fixture
def billing_database() -> Iterator[tuple[Session, AsyncMock]]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Column-only tables exercise reads/writes without claiming PostgreSQL FK/lock parity.
    for model in (Payment, UsageLog, ProductPaymentEvent):
        Table(
            model.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                    # Stand in for PostgreSQL gen_random_uuid() on inserted rows.
                    server_default=text("(lower(hex(randomblob(16))))")
                    if column.name == "id"
                    else None,
                )
                for column in model.__table__.columns
            ),
        )
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.add.side_effect = sync_session.add
            session.flush.side_effect = sync_session.flush
            session.execute.side_effect = sync_session.execute
            session.scalar.side_effect = sync_session.scalar
            session.scalars.side_effect = sync_session.scalars
            session.get.side_effect = sync_session.get
            yield sync_session, session
    finally:
        engine.dispose()


def test_fact_mapping_keeps_tuple_order_exact_credit_and_decimal_money() -> None:
    snapshot_id, payment_id = uuid4(), uuid4()
    credit = Decimal(2**70 + 17)
    payment_ids = [payment_id]
    amount = Decimal("123456789012345.67")
    info = PersistenceMapper.billing_statistics_rows_to_info(
        (
            [(snapshot_id, 10, 20, credit)],
            [(snapshot_id, "KRW", "refund", amount, 2, payment_ids)],
        )
    )
    assert info.usage == [(snapshot_id, 10, 20, 2**70 + 17)]
    assert type(info.usage[0][3]) is int
    assert info.payments == [(snapshot_id, "KRW", "refund", amount, 2, payment_ids)]
    assert info.payments[0][3] is amount and info.payments[0][5] is payment_ids
    account = PersistenceMapper.account_usage_statistics_row_to_info(
        (2, 10, 20, credit)
    )
    assert account == Types.AccountUsageStatisticsInfo(2, 10, 20, 2**70 + 17)


def test_nullable_payment_mappers_and_explicit_event_fields() -> None:
    assert PersistenceMapper.payment_entity_to_info(None) is None
    assert PersistenceMapper.payment_event_entity_to_info(None) is None
    event_id, payment_id, product_id, snapshot_id, sale_id = [uuid4() for _ in range(5)]
    event = ProductPaymentEvent(
        id=event_id,
        payment_id=payment_id,
        product_id=product_id,
        product_snapshot_id=snapshot_id,
        sale_id=sale_id,
        kind="refund",
        amount=Decimal("0.17"),
        currency="USD",
        occurred_at=STAMP,
        attributed_at=STAMP - timedelta(days=10),
    )
    assert PersistenceMapper.payment_event_entity_to_info(
        event
    ) == Types.PaymentEventInfo(
        id=event_id,
        payment_id=payment_id,
        product_id=product_id,
        product_snapshot_id=snapshot_id,
        sale_id=sale_id,
        kind="refund",
        amount=Decimal("0.17"),
        currency="USD",
        occurred_at=STAMP,
        attributed_at=STAMP - timedelta(days=10),
    )


@pytest.mark.asyncio
async def test_usage_write_and_account_range_preserve_legacy_and_owner_scope(
    billing_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = billing_database
    user_id, product_id, snapshot_id = uuid4(), uuid4(), uuid4()
    command = Types.RecordUsageCommand(
        user_id=user_id,
        conversation_id=uuid4(),
        generation_id=uuid4(),
        product_id=product_id,
        product_snapshot_id=snapshot_id,
        model_id=uuid4(),
        reasoning_effort="low",
        input_tokens=10,
        output_tokens=3,
        cost_credit=7,
        latency_ms=None,
        created_at=STAMP,
    )
    entity = await Repository.create_usage_log(session, command)
    recorded = PersistenceMapper.usage_entity_to_info(entity)
    assert recorded.id == entity.id
    assert (
        entity.conversation_id,
        entity.generation_id,
        entity.product_id,
        entity.product_snapshot_id,
        entity.model_id,
        entity.reasoning_effort,
        entity.latency_ms,
    ) == (
        command.conversation_id,
        command.generation_id,
        product_id,
        snapshot_id,
        command.model_id,
        "low",
        None,
    )
    for owner, stamp, amount in [
        (user_id, STAMP, 5),
        (uuid4(), STAMP, 100),
        (user_id, STAMP - timedelta(seconds=1), 200),
        (user_id, STAMP + timedelta(days=1), 300),
    ]:
        sync_session.add(
            UsageLog(
                user_id=owner,
                model_id=uuid4(),
                conversation_id=None,
                generation_id=None,
                product_id=None,
                product_snapshot_id=None,
                reasoning_effort=None,
                input_tokens=amount,
                output_tokens=amount,
                cost_credit=amount,
                latency_ms=None,
                created_at=stamp,
            )
        )
    sync_session.flush()
    info = PersistenceMapper.account_usage_statistics_row_to_info(
        await Repository.get_account_usage_statistics(
            session,
            user_id,
            STAMP,
            STAMP + timedelta(days=1),
        )
    )
    assert info == Types.AccountUsageStatisticsInfo(2, 15, 8, 12)
    empty = PersistenceMapper.account_usage_statistics_row_to_info(
        await Repository.get_account_usage_statistics(
            session,
            uuid4(),
            STAMP,
            STAMP + timedelta(days=1),
        )
    )
    assert empty == Types.AccountUsageStatisticsInfo(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_event_write_decimal_aggregates_and_optional_lookups(
    billing_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = billing_database
    user_id, payment_id, product_id, snapshot_id = [uuid4() for _ in range(4)]
    sync_session.add(
        Payment(
            id=payment_id,
            user_id=user_id,
            amount=Decimal("10.00"),
            currency="USD",
            status="succeeded",
            pg_provider="test",
        )
    )
    sync_session.flush()
    assert await Repository.get_payment(session, uuid4()) is None
    payment = PersistenceMapper.payment_entity_to_info(
        await Repository.get_payment(session, payment_id)
    )
    assert payment == Types.PaymentInfo(
        payment_id, "succeeded", Decimal("10.00"), "USD"
    )
    assert await Repository.get_first_payment_allocation(session, payment_id) is None
    assert await Repository.get_payment_event_by_key(session, "missing") is None
    assert await Repository.get_payment_event(session, uuid4()) is None
    assert await Repository.sum_payment_allocations(session, payment_id) == Decimal(0)
    sale = await Repository.create_payment_event(
        session,
        payment_id=payment_id,
        product_id=product_id,
        product_snapshot_id=snapshot_id,
        event_key="sale",
        kind="sale",
        amount=Decimal("1.13"),
        currency="USD",
        occurred_at=STAMP,
        attributed_at=STAMP,
    )
    assert sale.sale_id is None
    refund = await Repository.create_payment_event(
        session,
        payment_id=payment_id,
        product_id=product_id,
        product_snapshot_id=snapshot_id,
        event_key="refund",
        kind="refund",
        amount=Decimal("0.17"),
        currency="USD",
        sale_id=sale.id,
        occurred_at=STAMP + timedelta(days=2),
        attributed_at=STAMP,
    )
    sync_session.expire_all()
    found = PersistenceMapper.payment_event_entity_to_info(
        await Repository.get_payment_event_by_key(session, "refund")
    )
    assert found is not None and found.sale_id == sale.id
    assert found.amount == Decimal("0.17") and found.currency == "USD"
    # SQLite loses timezone metadata; compare persisted times in its local representation.
    assert found.occurred_at == (STAMP + timedelta(days=2)).replace(tzinfo=None)
    assert found.attributed_at == STAMP.replace(tzinfo=None)
    assert found.id == refund.id
    assert await Repository.get_first_payment_allocation(
        session, payment_id
    ) == STAMP.replace(tzinfo=None)
    assert await Repository.sum_payment_allocations(session, payment_id) == Decimal(
        "1.13"
    )
    assert await Repository.sum_sale_refunds(session, sale.id) == Decimal("0.17")
    assert await Repository.sum_sale_refunds(session, uuid4()) == Decimal(0)
