"""Offline product reporting scopes, SQL aggregates and read-only service contracts."""

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_statistics_contracts import (
    core_database as core_database_fixture,
)
from test_product_statistics_contracts import (
    statistics_database as statistics_database_fixture,
)

from app.core.reporting import ReportingError
from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)
from app.modules.content.product import types
from app.modules.content.product.mapper import reporting as Mapper
from app.modules.content.product.repository import reporting as Repository
from app.modules.content.product.service.query import reporting as QueryService

core_database = core_database_fixture
statistics_database = statistics_database_fixture


@pytest.fixture
def reporting_database(statistics_database):
    sync_session, session = statistics_database
    product_id, other_id, snapshot_id, other_snapshot, user_id, other_user = [
        uuid4() for _ in range(6)
    ]
    day = date(2026, 10, 15)
    old = datetime(2026, 10, 16, tzinfo=UTC)
    new = old + timedelta(hours=1)

    def metrics(model, product, stamp, updated_at, value, **extra):
        return model(
            product_id=product,
            day=stamp,
            updated_at=updated_at,
            active_users=1,
            revenue={"USD": {"secret": "not a reporting field"}},
            **dict.fromkeys(Repository.COUNTERS, value),
            **extra,
        )

    first = metrics(ProductDailyStats, product_id, day, old, 0)
    for value, field in enumerate(Repository.COUNTERS, start=1):
        setattr(first, field, value)
    sync_session.add_all(
        [
            first,
            metrics(ProductDailyStats, product_id, day + timedelta(days=1), new, 0),
            metrics(ProductDailyStats, other_id, day, old, 100),
            metrics(ProductDailyStats, product_id, day - timedelta(days=1), old, 900),
            metrics(
                ProductVersionDailyStats,
                product_id,
                day,
                new,
                7,
                product_snapshot_id=snapshot_id,
            ),
            metrics(
                ProductVersionDailyStats,
                product_id,
                day + timedelta(days=1),
                new,
                400,
                product_snapshot_id=other_snapshot,
            ),
            *[
                ProductUserDailyActivity(product_id=product, day=stamp, user_id=user)
                for product, stamp, user in (
                    (product_id, day, user_id),
                    (product_id, day + timedelta(days=1), user_id),
                    (other_id, day, user_id),
                    (other_id, day, other_user),
                )
            ],
            ProductVersionUserDailyActivity(
                product_id=product_id,
                product_snapshot_id=snapshot_id,
                day=day,
                user_id=user_id,
            ),
            ProductVersionUserDailyActivity(
                product_id=product_id,
                product_snapshot_id=other_snapshot,
                day=day + timedelta(days=1),
                user_id=other_user,
            ),
            ProductStatsDirtyDay(
                product_id=product_id,
                day=day + timedelta(days=2),
                requested_at=new,
            ),
            ProductStatsDirtyDay(product_id=other_id, day=day, requested_at=old),
            ProductStatsDirtyDay(
                product_id=product_id,
                day=day - timedelta(days=1),
                requested_at=old - timedelta(hours=1),
            ),
        ]
    )
    sync_session.flush()
    command = types.GetReportingStatisticsCommand(
        actor_id=uuid4(),
        product_id=product_id,
        date_from=day,
        date_to=day + timedelta(days=2),
    )
    return sync_session, session, command, snapshot_id, old, new


@pytest.mark.asyncio
async def test_product_and_version_scopes_keep_missing_zero_and_distinct_users(
    reporting_database,
):
    _sync, session, command, snapshot_id, old, new = reporting_database
    row = await Repository.get_product_reporting_statistics(
        session, command.product_id, command.date_from, command.date_to, None
    )
    info = Mapper.product_reporting_row_to_info(row, command)
    assert row.rows is row.root_rows
    assert info.recorded_totals.active_users == 1
    assert [getattr(info.recorded_totals, field) for field in Mapper.COUNTERS] == list(
        range(1, 11)
    )
    assert info.state == "pending" and info.totals is None
    assert info.missing_days == info.pending_days == (command.date_to,)
    assert [item.state for item in info.days] == ["collected", "collected", "pending"]
    assert info.days[1].metrics.succeeded == 0 and info.days[2].metrics is None
    assert info.oldest_updated_at.replace(tzinfo=UTC) == old
    assert info.newest_updated_at.replace(tzinfo=UTC) == new
    assert "revenue" not in asdict(info.recorded_totals)

    version_command = replace(
        command, snapshot_id=snapshot_id, date_to=command.date_to - timedelta(days=1)
    )
    version_row = await Repository.get_product_reporting_statistics(
        session,
        command.product_id,
        version_command.date_from,
        version_command.date_to,
        snapshot_id,
    )
    version = Mapper.product_reporting_row_to_info(version_row, version_command)
    assert version.state == "complete" and version.totals.active_users == 1
    assert version.totals.succeeded == 7
    assert version.days[1].metrics.active_users == 0
    assert version.days[1].metrics.succeeded == 0
    assert version.days[1].updated_at == version_row.root_rows[1].updated_at


@pytest.mark.asyncio
async def test_service_period_sums_cross_product_distinct_and_global_queue(
    reporting_database,
):
    sync_session, session, command, _snapshot_id, old, new = reporting_database
    row = await Repository.get_service_reporting_statistics(
        session, command.date_from, command.date_to
    )
    info = Mapper.service_reporting_row_to_info(row)
    assert info.product_days == 3 and info.products_with_rows == 2
    assert info.recorded_totals.active_users == 2
    assert [getattr(info.recorded_totals, field) for field in Mapper.COUNTERS] == list(
        range(101, 111)
    )
    assert info.oldest_updated_at.replace(tzinfo=UTC) == old
    assert info.newest_updated_at.replace(tzinfo=UTC) == new
    assert info.pending_product_days == 2
    assert info.oldest_pending_at.replace(tzinfo=UTC) == old
    queue = Mapper.statistics_queue_row_to_info(
        await Repository.get_statistics_queue(session)
    )
    assert queue.pending_product_days == 3
    assert queue.oldest_requested_at.replace(tzinfo=UTC) == old - timedelta(hours=1)
    assert (
        sync_session.scalar(select(func.count()).select_from(ProductStatsDirtyDay)) == 3
    )


@pytest.mark.asyncio
async def test_empty_aggregate_null_timestamps_do_not_become_confirmed_zero(
    statistics_database,
):
    _sync, session = statistics_database
    day = date(2026, 10, 15)
    info = Mapper.service_reporting_row_to_info(
        await Repository.get_service_reporting_statistics(session, day, day)
    )
    assert info.recorded_totals is None and info.product_days == 0
    assert info.products_with_rows == 0 and info.pending_product_days == 0
    assert (
        info.oldest_updated_at
        is info.newest_updated_at
        is info.oldest_pending_at
        is None
    )
    assert Mapper.statistics_queue_row_to_info(
        await Repository.get_statistics_queue(session)
    ) == types.StatisticsQueueInfo(0, None)


def test_bigint_decimal_sums_remain_exact_integer_usage_without_revenue():
    values = [Decimal(2**70 + index) for index in range(10)]
    row = Repository.ServiceReportingRow((1, 1, None, None, *values), 2, (0, None))
    info = Mapper.service_reporting_row_to_info(row)
    assert [getattr(info.recorded_totals, field) for field in Mapper.COUNTERS] == [
        int(value) for value in values
    ]
    assert all(type(value) is int for value in asdict(info.recorded_totals).values())


@pytest.fixture
def query_backend(monkeypatch):
    day = date(2026, 10, 15)
    command = types.GetReportingStatisticsCommand(
        actor_id=uuid4(),
        product_id=uuid4(),
        date_from=day,
        date_to=day,
        snapshot_id=uuid4(),
    )
    now = datetime(2026, 10, 16, tzinfo=UTC)
    state = types.ProductStateInfo(
        id=command.product_id,
        title="Private",
        description=None,
        opening_message=None,
        visibility="private",
        status="draft",
        created_at=now,
        updated_at=now,
        owner_id=uuid4(),
        default_model_id=None,
        reasoning_effort=None,
        replacement_policy={},
        latest_snapshot_id=None,
    )
    mocks = {
        "active": AsyncMock(),
        "admin": AsyncMock(),
        "owner": AsyncMock(),
        "state": AsyncMock(return_value=state),
        "snapshot": AsyncMock(
            return_value=types.ProductSnapshotInfo(
                command.snapshot_id, command.product_id, 1, {}, None, None
            )
        ),
        "read": AsyncMock(return_value=Repository.ProductReportingRow([], [], 0, [])),
        "service": AsyncMock(
            return_value=Repository.ServiceReportingRow(
                (0, 0, None, None, *([0] * 10)), 0, (0, None)
            )
        ),
        "queue": AsyncMock(return_value=(0, None)),
    }
    for target, name, key in (
        (QueryService.IdentityQueryService, "require_active_user", "active"),
        (QueryService.IdentityQueryService, "require_admin", "admin"),
        (QueryService.QueryService, "get_owned_product", "owner"),
        (QueryService.QueryService, "get_product_state", "state"),
        (QueryService.QueryService, "get_product_snapshot", "snapshot"),
        (Repository, "get_product_reporting_statistics", "read"),
        (Repository, "get_service_reporting_statistics", "service"),
        (Repository, "get_statistics_queue", "queue"),
    ):
        monkeypatch.setattr(target, name, mocks[key])
    return command, mocks


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_owner_and_admin_queries_disable_autoflush_restore_it_and_scope_ids(
    query_backend, role
):
    command, mocks = query_backend

    async def read(session, product_id, date_from, date_to, snapshot_id):
        assert session.autoflush is False
        assert (product_id, date_from, date_to, snapshot_id) == (
            command.product_id,
            command.date_from,
            command.date_to,
            command.snapshot_id,
        )
        return Repository.ProductReportingRow([], [], 0, [])

    mocks["read"].side_effect = read
    function = (
        QueryService.get_owner_reporting_statistics
        if role == "owner"
        else QueryService.get_admin_reporting_statistics
    )
    async with AsyncSession() as session:
        info = await function(session, command)
        assert session.autoflush is True and not session.in_transaction()
    assert info.state == "empty"
    mocks["snapshot"].assert_awaited_once()
    if role == "owner":
        assert mocks["owner"].await_args.args[1] == types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.actor_id
        )
        assert mocks["active"].await_args.args[1].user_id == command.actor_id
        mocks["admin"].assert_not_awaited()
    else:
        assert mocks["admin"].await_args.args[1].user_id == command.actor_id
        mocks["owner"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["inactive", "not_owner", "not_admin", "missing_product", "foreign_version"],
)
async def test_denied_scope_never_reads_statistics_and_restores_autoflush(
    query_backend, failure
):
    command, mocks = query_backend
    function = QueryService.get_owner_reporting_statistics
    if failure in ("inactive", "not_owner"):
        mocks["active" if failure == "inactive" else "owner"].side_effect = LookupError(
            "denied"
        )
    elif failure == "foreign_version":
        mocks["snapshot"].return_value = replace(
            mocks["snapshot"].return_value, product_id=uuid4()
        )
    else:
        function = QueryService.get_admin_reporting_statistics
        if failure == "not_admin":
            mocks["admin"].side_effect = LookupError("denied")
        else:
            mocks["state"].return_value = None
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await function(session, command)
        assert session.autoflush is True
    mocks["read"].assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_period_is_rejected_before_identity_or_repository(query_backend):
    command, mocks = query_backend
    command = replace(command, date_to=command.date_from - timedelta(days=1))
    async with AsyncSession() as session:
        with pytest.raises(ReportingError, match="invalid_period"):
            await QueryService.get_owner_reporting_statistics(session, command)
    mocks["active"].assert_not_awaited()
    mocks["read"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["service", "queue"])
async def test_global_read_requires_admin_before_repository(query_backend, scope):
    command, mocks = query_backend
    mocks["admin"].side_effect = LookupError("denied")
    async with AsyncSession() as session:
        with pytest.raises(LookupError, match="denied"):
            if scope == "service":
                await QueryService.get_recorded_service_statistics(
                    session,
                    types.GetServiceReportingStatisticsCommand(
                        actor_id=command.actor_id,
                        date_from=command.date_from,
                        date_to=command.date_to,
                    ),
                )
            else:
                await QueryService.get_statistics_queue(
                    session, types.GetStatisticsQueueCommand(actor_id=command.actor_id)
                )
        assert session.autoflush is True
    mocks[scope].assert_not_awaited()
