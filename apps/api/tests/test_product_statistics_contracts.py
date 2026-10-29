"""Exact monetary/count aggregation and offline report/rebuild contracts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import JSON, Column, MetaData, Table, Uuid, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_core_contracts import database as core_database_fixture

from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)
from app.modules.content.product import types
from app.modules.content.product.mapper import statistics as Mapper
from app.modules.content.product.repository import statistics as Repository
from app.modules.content.product.service.command import statistics as CommandService

core_database = core_database_fixture


def facts(product_id=None, day=date(2026, 10, 26)):
    return types.ReplaceStatisticsDayCommand(
        product_id=product_id or uuid4(),
        day=day,
        generations=[],
        users=[],
        conversations=[],
        transitions=[],
        usage=[],
        payments=[],
    )


def sample_facts(product_id=None, day=date(2026, 10, 26)):
    first, second, user, other_user, payment, other_payment, krw_payment = [
        uuid4() for _ in range(7)
    ]
    value = types.ReplaceStatisticsDayCommand(
        product_id=product_id or uuid4(),
        day=day,
        generations=[
            (first, "succeeded", 2, 3),
            (first, "failed", 1, None),
            (second, "cancelled", 1, 0),
            (second, "stale", 2, 0),
        ],
        users=[(first, user), (first, other_user), (second, user)],
        conversations=[(first, 2), (second, 1)],
        transitions=[(second, 3)],
        usage=[(first, 10, 20, 30), (second, 40, 50, 60)],
        payments=[
            (first, "USD", "sale", Decimal("0.10"), 2, [payment, other_payment]),
            (second, "USD", "sale", Decimal("0.20"), 1, [payment]),
            (first, "USD", "refund", Decimal("0.15"), 1, [payment]),
            (first, "KRW", "sale", Decimal("1000"), 1, [krw_payment]),
            (second, "KRW", "refund", Decimal("50"), 2, [krw_payment]),
        ],
    )
    return value, first, second, user, other_user


def test_fact_aggregation_keeps_version_counts_distinct_users_and_exact_currencies():
    value, first, second, user, other_user = sample_facts()
    build = Mapper.statistics_facts_infos_to_build_info(value)
    assert build.metrics[first]["active_users"] == 2
    assert build.metrics[second]["active_users"] == 1
    assert build.total["active_users"] == 2 and build.unique_users == {user, other_user}
    assert [build.total[key] for key in Mapper.COUNTERS] == [
        2,
        1,
        1,
        2,
        3,
        3,
        3,
        50,
        70,
        90,
    ]
    assert build.total["revenue"] == {
        "USD": {
            "sales": "0.30",
            "refunds": "0.15",
            "net": "0.15",
            "sale_count": 2,
            "refund_count": 1,
        },
        "KRW": {
            "sales": "1000",
            "refunds": "50",
            "net": "950",
            "sale_count": 1,
            "refund_count": 2,
        },
    }
    assert build.metrics[first]["revenue"]["USD"]["net"] == "-0.05"
    assert build.metrics[second]["revenue"]["USD"]["net"] == "0.20"
    assert build.users == value.users
    build.metrics[first]["revenue"]["USD"]["sales"] = "changed"
    assert build.total["revenue"]["USD"]["sales"] == "0.30"


def test_empty_facts_keep_zero_metrics_and_unexpected_status_is_not_hidden():
    value = facts()
    build = Mapper.statistics_facts_infos_to_build_info(value)
    assert build.metrics == {} and build.unique_users == set()
    assert all(build.total[key] == 0 for key in Mapper.COUNTERS)
    assert build.total["active_users"] == 0 and build.total["revenue"] == {}
    value.generations.append((uuid4(), "pending", 1, 0))
    with pytest.raises(KeyError, match="pending"):
        Mapper.statistics_facts_infos_to_build_info(value)


@pytest.fixture
def statistics_database(core_database):
    sync_session, session = core_database
    metadata = MetaData()
    for model in (
        ProductDailyStats,
        ProductVersionDailyStats,
        ProductUserDailyActivity,
        ProductVersionUserDailyActivity,
        ProductStatsDirtyDay,
    ):
        columns = []
        for column in model.__table__.columns:
            column_type = JSON() if isinstance(column.type, JSONB) else column.type
            if isinstance(column_type, Uuid):
                column_type = Uuid(native_uuid=False)
            columns.append(
                Column(
                    column.name,
                    column_type,
                    primary_key=column.primary_key,
                    server_default=text("CURRENT_TIMESTAMP")
                    if column.name in ("updated_at", "requested_at")
                    else None,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(sync_session.get_bind())
    session.add_all.side_effect = sync_session.add_all
    yield sync_session, session


@pytest.mark.asyncio
async def test_rebuild_is_idempotent_and_report_uses_period_distinct_users(
    statistics_database,
):
    sync_session, session = statistics_database
    value, first, _second, user, _other_user = sample_facts()
    now = datetime.now(UTC)
    build = Mapper.statistics_facts_infos_to_build_info(value)
    await Repository.replace_statistics_day(
        session, value.product_id, value.day, build, now
    )
    await Repository.replace_statistics_day(
        session, value.product_id, value.day, build, now
    )
    assert sync_session.scalar(select(func.count()).select_from(ProductDailyStats)) == 1
    assert (
        sync_session.scalar(select(func.count()).select_from(ProductVersionDailyStats))
        == 2
    )
    assert (
        sync_session.scalar(select(func.count()).select_from(ProductUserDailyActivity))
        == 2
    )
    assert (
        sync_session.scalar(
            select(func.count()).select_from(ProductVersionUserDailyActivity)
        )
        == 3
    )
    next_day = value.day + timedelta(days=1)
    later = facts(value.product_id, next_day)
    later.users.append((first, user))
    await Repository.replace_statistics_day(
        session,
        value.product_id,
        next_day,
        Mapper.statistics_facts_infos_to_build_info(later),
        now,
    )
    missing_day = value.day - timedelta(days=1)
    sync_session.add(
        ProductStatsDirtyDay(
            product_id=value.product_id, day=missing_day, requested_at=now
        )
    )
    sync_session.flush()
    report = await Repository.get_statistics_report(
        session, value.product_id, missing_day, next_day, None
    )
    result = Mapper.statistics_report_row_to_info(
        report, value.product_id, None, missing_day, next_day
    )
    assert [row.day for row in result.days] == [value.day, next_day]
    assert [row.active_users for row in result.days] == [2, 1]
    assert result.totals.active_users == 2
    assert result.pending_days == [missing_day]
    assert result.totals.revenue["USD"].net == "0.15"
    version_report = await Repository.get_statistics_report(
        session, value.product_id, missing_day, next_day, first
    )
    version = Mapper.statistics_report_row_to_info(
        version_report, value.product_id, first, missing_day, next_day
    )
    assert version.totals.active_users == 2 and version.totals.succeeded == 2
    assert version.totals.revenue["USD"].net == "-0.05"
    empty = await Repository.get_statistics_report(
        session, uuid4(), missing_day, next_day, None
    )
    assert empty == ([], 0, [])


@pytest.mark.asyncio
async def test_failed_replace_propagates_and_preserves_rows_after_caller_rollback(
    statistics_database,
):
    sync_session, session = statistics_database
    value, *_ = sample_facts()
    now = datetime.now(UTC)
    await Repository.replace_statistics_day(
        session,
        value.product_id,
        value.day,
        Mapper.statistics_facts_infos_to_build_info(value),
        now,
    )
    count = 0

    def execute_then_fail(statement, *args, **kwargs):
        nonlocal count
        count += 1
        result = sync_session.execute(statement, *args, **kwargs)
        if count == 2:
            raise RuntimeError("Interrupted replacement")
        return result

    session.execute.side_effect = execute_then_fail
    with pytest.raises(RuntimeError, match="Interrupted replacement"):
        with sync_session.begin_nested():
            await Repository.replace_statistics_day(
                session,
                value.product_id,
                value.day,
                Mapper.statistics_facts_infos_to_build_info(facts(value.product_id)),
                now,
            )
    assert sync_session.scalars(select(ProductDailyStats)).one().succeeded == 2
    assert (
        sync_session.scalar(select(func.count()).select_from(ProductVersionDailyStats))
        == 2
    )


@pytest.mark.asyncio
async def test_queue_claim_order_and_completion_are_product_day_scoped(
    statistics_database,
):
    sync_session, session = statistics_database
    product_id, other_id = uuid4(), uuid4()
    day, now = date(2026, 10, 27), datetime.now(UTC)
    oldest = ProductStatsDirtyDay(
        product_id=other_id, day=day, requested_at=now - timedelta(hours=1)
    )
    newer = ProductStatsDirtyDay(product_id=product_id, day=day, requested_at=now)
    sync_session.add_all([newer, oldest])
    sync_session.flush()
    assert await Repository.get_pending_statistics_work(session) is oldest
    await Repository.delete_statistics_work(session, other_id, day)
    assert await Repository.get_pending_statistics_work(session) is newer
    await Repository.delete_statistics_work(session, product_id, day)
    assert await Repository.get_pending_statistics_work(session) is None


@pytest.mark.asyncio
async def test_enqueue_recent_keeps_inclusive_days_and_seoul_boundaries(monkeypatch):
    ids = [uuid4(), uuid4()]
    monkeypatch.setattr(
        CommandService.Repository,
        "list_published_product_ids",
        AsyncMock(return_value=ids),
    )
    upsert = AsyncMock()
    monkeypatch.setattr(Repository, "upsert_statistics_work", upsert)
    async with AsyncSession() as session:
        await CommandService.enqueue_recent(
            session,
            types.EnqueueRecentCommand(
                days=2, now=datetime(2026, 10, 26, 15, tzinfo=UTC)
            ),
        )
        assert not session.in_transaction()
    assert [(call.args[1], call.args[2]) for call in upsert.await_args_list] == [
        (product_id, day)
        for product_id in ids
        for day in (date(2026, 10, 27), date(2026, 10, 26), date(2026, 10, 25))
    ]
