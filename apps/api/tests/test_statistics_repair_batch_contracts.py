"""SQLite SQL/transactions through an async adapter; PG syntax, not PG locking."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Column,
    Connection,
    Date,
    DateTime,
    ForeignKey,
    MetaData,
    Table,
    Text,
    Uuid,
    create_engine,
    event,
    select,
    text,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import ClauseElement

from app.db.models.product_statistics import ProductStatsDirtyDay
from app.db.product_stats_queue import day_bounds, statistics_day
from app.db.transaction import use_case_transaction
from app.modules.content.product import statistics_job as Job
from app.modules.content.product import types as Types
from app.modules.content.product.repository import statistics as Repository
from app.modules.content.product.service.command import statistics as Service
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)
from app.use_cases import product_statistics as UseCase

NOW = datetime(2026, 10, 28, 15, tzinfo=UTC)
TODAY = date(2026, 10, 29)


@dataclass
class Backend:
    store: Session
    session: AsyncSession
    products: Table
    statements: list[str]
    requests: list[tuple[str, dict[str, object]]]
    transactions: list[str]

    def add_products(self, count: int) -> list[UUID]:
        product_ids = [UUID(int=index + 1) for index in range(count)]
        if product_ids:
            self.store.execute(
                self.products.insert(),
                [
                    {"id": product_id, "latest_snapshot_id": uuid4()}
                    for product_id in product_ids
                ],
            )
        self.store.commit()
        self.statements.clear()
        self.requests.clear()
        return product_ids

    def keys(self) -> set[tuple[UUID, date]]:
        return set(
            self.store.execute(
                select(ProductStatsDirtyDay.product_id, ProductStatsDirtyDay.day)
            ).tuples()
        )


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Iterator[Backend]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    products = Table(
        "products",
        metadata,
        Column("id", Uuid(native_uuid=False), primary_key=True),
        Column("latest_snapshot_id", Uuid(native_uuid=False)),
        Column("status", Text, server_default="draft"),
        Column("visibility", Text, server_default="private"),
    )
    Table(
        "product_stats_dirty_days",
        metadata,
        Column(
            "product_id",
            Uuid(native_uuid=False),
            ForeignKey("products.id"),
            primary_key=True,
        ),
        Column("day", Date, primary_key=True),
        Column(
            "requested_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    metadata.create_all(engine)
    statements: list[str] = []
    requests: list[tuple[str, dict[str, object]]] = []
    transactions: list[str] = []

    def executed(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", executed)
    try:
        with Session(engine, expire_on_commit=False) as store:
            session = AsyncSession()

            def committed(session: Session) -> None:
                store.commit()
                transactions.append("commit")

            def rolled_back(session: Session) -> None:
                store.rollback()
                transactions.append("rollback")

            def requested(state: ORMExecuteState) -> None:
                statement = state.statement
                assert isinstance(statement, ClauseElement)
                compiled = statement.compile(dialect=postgresql.dialect())
                requests.append((str(compiled), dict(compiled.params or {})))

            event.listen(session.sync_session, "after_commit", committed)
            event.listen(session.sync_session, "after_rollback", rolled_back)
            event.listen(store, "do_orm_execute", requested)
            for name, operation in (
                ("execute", store.execute),
                ("scalars", store.scalars),
                ("scalar", store.scalar),
            ):
                monkeypatch.setattr(session, name, AsyncMock(side_effect=operation))
            yield Backend(store, session, products, statements, requests, transactions)
            session.sync_session.close()
    finally:
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("product_count", "days"),
    [(0, 31), (1, 1), (1, 31), (3, 7), (16, 31), (249, 1), (250, 1), (251, 1)],
)
async def test_repair_sql_counts(
    backend: Backend, product_count: int, days: int
) -> None:
    product_ids = backend.add_products(product_count)
    await Service.enqueue_recent(
        backend.session, Types.EnqueueRecentCommand(days=days, now=NOW)
    )
    inserts = sum(sql.startswith("INSERT") for sql in backend.statements)
    selects = sum(sql.startswith("SELECT") for sql in backend.statements)
    print(
        f"U25_SQL products={product_count} days={days}: SELECT={selects} UPSERT={inserts}"
    )
    assert selects == 1
    assert inserts == (product_count * (days + 1) + 499) // 500
    assert backend.keys() == {
        (product_id, TODAY - timedelta(days=offset))
        for product_id in product_ids
        for offset in range(days + 1)
    }
    assert backend.transactions == ["commit"]
    assert not backend.session.in_transaction()


def request_keys(params: dict[str, object]) -> list[tuple[UUID, date]]:
    keys = []
    for name, product_id in params.items():
        if name.startswith("product_id"):
            day = params[name.replace("product_id", "day", 1)]
            assert isinstance(product_id, UUID) and isinstance(day, date)
            keys.append((product_id, day))
    return keys


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 499, 500, 501, 1001])
async def test_repository_streams_bounded_statements_and_last_partial_batch(
    backend: Backend, count: int
) -> None:
    product_id = backend.add_products(1)[0]

    def work() -> Iterator[tuple[UUID, date]]:
        for index in range(count):
            # The next chunk must not be read until the previous SQL has run.
            assert index // 500 == len(backend.requests)
            yield product_id, TODAY - timedelta(days=index)

    async with use_case_transaction(backend.session):
        await Repository.upsert_statistics_work_batch(backend.session, work())
    expected_sizes = [500] * (count // 500) + ([count % 500] if count % 500 else [])
    assert [
        len(request_keys(params)) for _, params in backend.requests
    ] == expected_sizes
    for sql, params in backend.requests:
        assert "ON CONFLICT (product_id, day) DO UPDATE SET requested_at = now()" in sql
        assert "requested_at" not in params  # INSERT keeps the DB server default.
        assert len(params) <= 1000
    assert len(backend.keys()) == count


@pytest.mark.asyncio
async def test_duplicate_keys_are_unique_in_each_pg_statement(backend: Backend) -> None:
    product_id = backend.add_products(1)[0]
    keys = [(product_id, TODAY), (product_id, TODAY - timedelta(days=1))]
    async with use_case_transaction(backend.session):
        await Repository.upsert_statistics_work_batch(
            backend.session, (keys[index % 2] for index in range(1003))
        )
    assert len(backend.requests) == 3
    for _, params in backend.requests:
        batch = request_keys(params)
        assert len(batch) == len(set(batch)) == 2
    assert backend.keys() == set(keys)


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [-1, 0, 32, 100])
async def test_invalid_days_fail_before_query_or_transaction(
    backend: Backend, days: int
) -> None:
    with pytest.raises(ValueError, match="Repair range must be 1–31 days"):
        await Service.enqueue_recent(
            backend.session, Types.EnqueueRecentCommand(days=days, now=NOW)
        )
    assert backend.statements == backend.transactions == []
    assert not backend.session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("now", "today"),
    [
        (datetime(2026, 10, 28, 14, 59, 59, 999999, tzinfo=UTC), date(2026, 10, 28)),
        (NOW, TODAY),
        (datetime(2025, 12, 31, 15, tzinfo=UTC), date(2026, 1, 1)),
        (datetime(2024, 2, 29, 15, tzinfo=UTC), date(2024, 3, 1)),
    ],
)
async def test_repair_dates_match_single_service_seoul_conversion(
    backend: Backend, now: datetime, today: date
) -> None:
    product_id = backend.add_products(1)[0]
    await Service.enqueue_recent(
        backend.session, Types.EnqueueRecentCommand(days=1, now=now)
    )
    expected = {today, today - timedelta(days=1)}
    assert backend.keys() == {(product_id, day) for day in expected}
    assert {statistics_day(day_bounds(day)[0]) for day in expected} == expected


@pytest.mark.asyncio
async def test_naive_timestamp_is_rejected_without_writes(backend: Backend) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await Service.enqueue_recent(
            backend.session, Types.EnqueueRecentCommand(now=datetime(2026, 10, 29))
        )
    assert backend.statements == backend.transactions == []


@pytest.mark.asyncio
async def test_only_snapshot_presence_selects_products(backend: Backend) -> None:
    ids = [uuid4() for _ in range(4)]
    backend.store.execute(
        backend.products.insert(),
        [
            {
                "id": ids[0],
                "latest_snapshot_id": uuid4(),
                "status": "draft",
                "visibility": "private",
            },
            {
                "id": ids[1],
                "latest_snapshot_id": uuid4(),
                "status": "approved",
                "visibility": "public",
            },
            {
                "id": ids[2],
                "latest_snapshot_id": uuid4(),
                "status": "rejected",
                "visibility": "unlisted",
            },
            {
                "id": ids[3],
                "latest_snapshot_id": None,
                "status": "approved",
                "visibility": "public",
            },
        ],
    )
    backend.store.commit()
    await Service.enqueue_recent(
        backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
    )
    assert backend.keys() == {
        (product_id, day)
        for product_id in ids[:3]
        for day in (TODAY, TODAY - timedelta(days=1))
    }


@pytest.mark.asyncio
async def test_single_service_and_repair_refresh_existing_request_time(
    backend: Backend,
) -> None:
    product_id = backend.add_products(1)[0]
    old = datetime(2000, 1, 1, tzinfo=UTC)
    untouched_day = TODAY - timedelta(days=20)
    backend.store.add_all(
        ProductStatsDirtyDay(product_id=product_id, day=day, requested_at=old)
        for day in (TODAY, untouched_day)
    )
    backend.store.commit()
    backend.store.expunge_all()
    # command.now determines the date only; requested_at comes from the DB.
    await Service.enqueue_recent(
        backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
    )
    rows = {
        row.day: row.requested_at
        for row in backend.store.scalars(select(ProductStatsDirtyDay))
    }
    assert set(rows) == {TODAY, TODAY - timedelta(days=1), untouched_day}
    assert rows[untouched_day].replace(tzinfo=UTC) == old
    assert rows[TODAY].replace(tzinfo=UTC) > old
    backend.store.execute(
        update(ProductStatsDirtyDay)
        .where(ProductStatsDirtyDay.day == TODAY)
        .values(requested_at=old)
    )
    backend.store.commit()
    await mark_statistics_dirty(
        backend.session,
        Types.MarkStatisticsDirtyCommand(product_id=product_id, instant=NOW),
    )
    await mark_statistics_dirty(
        backend.session,
        Types.MarkStatisticsDirtyCommand(
            product_id=product_id, instant=NOW - timedelta(days=2)
        ),
    )
    assert len(backend.keys()) == 4
    refreshed = backend.store.scalar(
        select(ProductStatsDirtyDay.requested_at).where(
            ProductStatsDirtyDay.day == TODAY
        )
    )
    assert refreshed is not None and refreshed.replace(tzinfo=UTC) > old


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_batch", [2, 3])
@pytest.mark.parametrize("caught", [False, True])
async def test_middle_batch_failure_rolls_back_all_outer_changes(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, failing_batch: int, caught: bool
) -> None:
    product_id = backend.add_products(501)[0]
    old = datetime(2000, 1, 1, tzinfo=UTC)
    backend.store.add(
        ProductStatsDirtyDay(product_id=product_id, day=TODAY, requested_at=old)
    )
    backend.store.commit()
    backend.store.expunge_all()
    calls = 0

    async def fail_after_write(statement: Executable) -> None:
        nonlocal calls
        backend.store.execute(statement)
        calls += 1
        if calls == failing_batch:
            raise RuntimeError("batch failed")

    monkeypatch.setattr(backend.session, "execute", fail_after_write)
    with pytest.raises(
        RuntimeError, match="nested use case failed" if caught else "batch failed"
    ):
        async with use_case_transaction(backend.session):
            backend.store.execute(update(backend.products).values(status="approved"))
            if caught:
                with pytest.raises(RuntimeError, match="batch failed"):
                    await Service.enqueue_recent(
                        backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
                    )
            else:
                await Service.enqueue_recent(
                    backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
                )
    assert calls == failing_batch
    assert backend.transactions == ["rollback"]
    assert backend.keys() == {(product_id, TODAY)}
    restored = backend.store.scalar(select(ProductStatsDirtyDay.requested_at))
    assert restored is not None and restored.replace(tzinfo=UTC) == old
    assert set(backend.store.scalars(select(backend.products.c.status))) == {"draft"}
    assert not backend.session.in_transaction()


@pytest.mark.asyncio
async def test_sql_failure_in_partial_batch_rolls_back_previous_batch(
    backend: Backend,
) -> None:
    product_id = backend.add_products(1)[0]

    def work() -> Iterator[tuple[UUID, date]]:
        for index in range(500):
            yield product_id, TODAY - timedelta(days=index)
        yield uuid4(), TODAY  # Real FK failure in the second, partial statement.

    with pytest.raises(IntegrityError):
        async with use_case_transaction(backend.session):
            await Repository.upsert_statistics_work_batch(backend.session, work())
    assert len(backend.requests) == 2
    assert backend.transactions == ["rollback"]
    assert backend.keys() == set()


@pytest.mark.asyncio
async def test_successful_enqueue_waits_for_outer_commit(backend: Backend) -> None:
    backend.add_products(1)
    with pytest.raises(ValueError, match="later failure"):
        async with use_case_transaction(backend.session):
            await Service.enqueue_recent(
                backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
            )
            assert backend.transactions == []
            assert len(backend.keys()) == 2
            raise ValueError("later failure")
    assert backend.transactions == ["rollback"]
    assert backend.keys() == set()


@pytest.mark.asyncio
async def test_unrelated_existing_transaction_is_not_adopted(backend: Backend) -> None:
    await backend.session.begin()
    with pytest.raises(InvalidRequestError, match="transaction is already begun"):
        await Service.enqueue_recent(
            backend.session, Types.EnqueueRecentCommand(days=1, now=NOW)
        )
    assert backend.statements == backend.transactions == []
    await backend.session.rollback()


@pytest.mark.asyncio
async def test_job_repair_claim_rebuild_complete_compatibility(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend.add_products(1)
    rebuilt: list[Types.RebuildDayCommand] = []

    async def rebuild(session: AsyncSession, command: Types.RebuildDayCommand) -> None:
        assert session is backend.session and session.in_transaction()
        rebuilt.append(command)

    engine = Mock()
    engine.dispose = AsyncMock()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused.invalid/test")
    monkeypatch.setattr(Job, "create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr(Job, "AsyncSession", Mock(return_value=backend.session))
    monkeypatch.setattr(UseCase, "rebuild_day", rebuild)
    await Job.run(limit=100, repair=True)
    assert len(rebuilt) == Types.EnqueueRecentCommand().days + 1
    assert backend.keys() == set()
    assert len(set(rebuilt_day.day for rebuilt_day in rebuilt)) == len(rebuilt)
    assert "FOR UPDATE SKIP LOCKED" in next(
        sql for sql, _ in backend.requests if "FOR UPDATE" in sql
    )
    assert capsys.readouterr().out == "Processed 8 product statistic days.\n"
    engine.dispose.assert_awaited_once_with()
