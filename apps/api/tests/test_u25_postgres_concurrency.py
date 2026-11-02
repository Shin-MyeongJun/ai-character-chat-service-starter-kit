"""U25 interleavings on real PG connections; barriers never replace SQL results."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypeVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import ScalarResult, Select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tag import Tag
from app.db.transaction import use_case_transaction
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command import statistics as StatisticsCommand
from app.modules.content.product.service.command import statistics_queue as QueueCommand
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommand

pytestmark = pytest.mark.asyncio
T = TypeVar("T")
U = TypeVar("U")
NOW = datetime(2026, 11, 2, 3, tzinfo=UTC)
TODAY = date(2026, 11, 2)


class RollbackLeader(Exception):
    """Roll back a successful leader operation after observing the follower wait."""


async def prepare_connection(session: AsyncSession) -> int:
    await session.execute(text("SET LOCAL statement_timeout = '10s'"))
    await session.execute(text("SET LOCAL lock_timeout = '8s'"))
    assert await session.scalar(text("SHOW transaction_isolation")) == "read committed"
    pid = await session.scalar(text("SELECT pg_backend_pid()"))
    assert isinstance(pid, int)
    return pid


async def wait_for_blocker(db: AsyncSession, leader: int, follower: int) -> None:
    async with AsyncSession(db.bind) as observer:
        async with asyncio.timeout(5):
            while not await observer.scalar(
                text("SELECT :leader = ANY(pg_blocking_pids(:follower))"),
                {"leader": leader, "follower": follower},
            ):
                await asyncio.sleep(0.01)


async def run_blocked(
    db: AsyncSession,
    first: Callable[[AsyncSession], Awaitable[T]],
    second: Callable[[AsyncSession], Awaitable[U]],
    *,
    rollback_first: bool = False,
    cancel_second: bool = False,
) -> tuple[T, U | None]:
    """Release the leader only after PG confirms a different backend is blocked."""
    follower_ready = asyncio.Event()
    follower_pid = 0

    async def run_second() -> U:
        nonlocal follower_pid
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            async with use_case_transaction(session):
                follower_pid = await prepare_connection(session)
                follower_ready.set()
                return await second(session)

    task: asyncio.Task[U] | None = None
    try:
        async with asyncio.timeout(20):
            async with AsyncSession(db.bind, expire_on_commit=False) as session:
                try:
                    async with use_case_transaction(session):
                        leader_pid = await prepare_connection(session)
                        first_result = await first(session)
                        task = asyncio.create_task(run_second())
                        await follower_ready.wait()
                        assert leader_pid != follower_pid
                        await wait_for_blocker(db, leader_pid, follower_pid)
                        if cancel_second:
                            task.cancel()
                            with pytest.raises(asyncio.CancelledError):
                                await task
                        if rollback_first:
                            raise RollbackLeader
                except RollbackLeader:
                    pass
            assert task is not None
            return first_result, None if cancel_second else await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def seed_admin(db: AsyncSession) -> UUID:
    actor_id = uuid4()
    async with use_case_transaction(db):
        await db.execute(
            text("INSERT INTO users(id,email,role) VALUES (:id,:email,'admin')"),
            {"id": actor_id, "email": f"{actor_id}@u25.test"},
        )
    return actor_id


async def test_overlapping_resolves_cross_batch_boundary(db: AsyncSession) -> None:
    names = tuple(f"tag-{index:04}" for index in range(501))

    async def first(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session, TagTypes.ResolveTagsCommand(names)
        )

    async def second(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session, TagTypes.ResolveTagsCommand((*reversed(names), "other"))
        )

    left, right = await run_blocked(db, first, second)
    assert right is not None
    assert tuple(info.name for info in right) == (*reversed(names), "other")
    assert {info.name: info.id for info in left} == {
        info.name: info.id for info in right if info.name != "other"
    }
    assert await db.scalar(text("SELECT count(*) FROM tags")) == 502


@pytest.mark.parametrize("action", ["rename", "deactivate"])
async def test_resolve_share_lock_delays_admin_change(
    db: AsyncSession, action: str
) -> None:
    actor = await seed_admin(db)
    tag = (await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("old",))))[0]

    async def resolve(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session, TagTypes.ResolveTagsCommand(("old", "new"))
        )

    async def change(session: AsyncSession) -> TagTypes.TagInfo:
        if action == "rename":
            return await TagCommand.update_tag(
                session, TagTypes.UpdateTagCommand(tag.id, actor, "renamed", "edited")
            )
        return await TagCommand.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(tag.id, actor)
        )

    resolved, changed = await run_blocked(db, resolve, change)
    assert resolved[0] == tag
    assert changed is not None and changed.id == tag.id
    row = (
        await db.execute(
            text("SELECT name,is_active FROM tags WHERE id=:id"), {"id": tag.id}
        )
    ).one()
    assert (row.name, row.is_active) == (
        ("renamed", True) if action == "rename" else ("old", False)
    )


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("rollback_admin", [False, True])
async def test_admin_deactivation_precedes_resolve(
    db: AsyncSession, retained: bool, rollback_admin: bool
) -> None:
    actor = await seed_admin(db)
    tag = (await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("old",))))[0]

    async def deactivate(session: AsyncSession) -> TagTypes.TagInfo:
        return await TagCommand.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(tag.id, actor)
        )

    async def resolve(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session,
            TagTypes.ResolveTagsCommand(
                ("a new", "old"), (tag.id,) if retained else ()
            ),
        )

    if not retained and not rollback_admin:
        with pytest.raises(ValueError, match="Inactive tags cannot be newly assigned"):
            await run_blocked(db, deactivate, resolve)
        assert (
            await db.scalar(text("SELECT count(*) FROM tags WHERE name='a new'")) == 0
        )
    else:
        _, resolved = await run_blocked(
            db, deactivate, resolve, rollback_first=rollback_admin
        )
        assert isinstance(resolved, tuple)
        assert resolved[1].id == tag.id
        assert resolved[1].is_active is rollback_admin


@pytest.mark.parametrize("creator_first", [False, True])
async def test_admin_create_and_resolve_wait_on_unique_name(
    db: AsyncSession, creator_first: bool
) -> None:
    actor = await seed_admin(db)

    async def create(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return (
            await TagCommand.create_tag(
                session, TagTypes.CreateTagCommand(actor, "shared", "admin description")
            ),
        )

    async def resolve(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session, TagTypes.ResolveTagsCommand(("shared",))
        )

    left, right = await run_blocked(
        db, create if creator_first else resolve, resolve if creator_first else create
    )
    assert right is not None and left == right
    assert left[0].description == ("admin description" if creator_first else None)
    assert await db.scalar(text("SELECT count(*) FROM tags")) == 1


@pytest.mark.parametrize("rollback_admin", [False, True])
async def test_admin_rename_precedes_resolve_insert(
    db: AsyncSession, rollback_admin: bool
) -> None:
    actor = await seed_admin(db)
    original = (
        await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("old",)))
    )[0]

    async def rename(session: AsyncSession) -> TagTypes.TagInfo:
        return await TagCommand.update_tag(
            session, TagTypes.UpdateTagCommand(original.id, actor, "renamed", "edited")
        )

    async def resolve(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session, TagTypes.ResolveTagsCommand(("old",))
        )

    _, resolved = await run_blocked(db, rename, resolve, rollback_first=rollback_admin)
    assert resolved is not None and resolved[0].name == "old"
    if rollback_admin:
        assert resolved == (original,)
    else:
        # Once the old unique name is freed, INSERT can create a new dictionary
        # ID. This differs from rename in the INSERT/SELECT gap below.
        assert resolved[0].id != original.id and resolved[0].description is None
    assert await db.scalar(text("SELECT count(*) FROM tags")) == (
        1 if rollback_admin else 2
    )


async def test_admin_rename_between_insert_and_share_rolls_back_resolve(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor = await seed_admin(db)
    tag = (await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("old",))))[0]
    reached_select, release_select = asyncio.Event(), asyncio.Event()
    async with AsyncSession(db.bind, expire_on_commit=False) as resolver:
        original_scalars = resolver.scalars

        async def pause_select(statement: Select[tuple[Tag]]) -> ScalarResult[Tag]:
            reached_select.set()
            await release_select.wait()
            return await original_scalars(statement)

        # Gate only the real resolver's SELECT; both writes use production SQL
        # on independent connections, and no rows/results are fabricated.
        monkeypatch.setattr(resolver, "scalars", pause_select)
        task = asyncio.create_task(
            TagCommand.resolve_tags(
                resolver, TagTypes.ResolveTagsCommand(("a new", "old"))
            )
        )
        try:
            async with asyncio.timeout(15):
                await reached_select.wait()
                changed = await TagCommand.update_tag(
                    db, TagTypes.UpdateTagCommand(tag.id, actor, "renamed")
                )
                release_select.set()
                with pytest.raises(ValueError, match="Tag name changed concurrently"):
                    await task
                assert changed.id == tag.id
        finally:
            release_select.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert (await db.execute(text("SELECT name FROM tags"))).scalars().all() == [
        "renamed"
    ]


async def test_cancel_blocked_resolve_rolls_back_prior_batch(db: AsyncSession) -> None:
    # The follower inserts 500 names before its second batch reaches the lock.
    actor = await seed_admin(db)
    tag = (await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("z",))))[0]

    async def hold(session: AsyncSession) -> TagTypes.TagInfo:
        return await TagCommand.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(tag.id, actor)
        )

    async def resolve(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
        return await TagCommand.resolve_tags(
            session,
            TagTypes.ResolveTagsCommand((*tuple(f"a-{n:04}" for n in range(500)), "z")),
        )

    await run_blocked(db, hold, resolve, cancel_second=True)
    assert await db.scalar(text("SELECT count(*) FROM tags")) == 1
    assert await db.scalar(text("SELECT is_active FROM tags WHERE name='z'")) is False


async def seed_products(db: AsyncSession, count: int = 1) -> list[UUID]:
    actor = await seed_admin(db)
    rows = [{"id": uuid4(), "snapshot": uuid4(), "owner": actor} for _ in range(count)]
    async with use_case_transaction(db):
        await db.execute(
            text("INSERT INTO products(id,owner_id,title) VALUES (:id,:owner,'U25')"),
            [{"id": row["id"], "owner": actor} for row in rows],
        )
        await db.execute(
            text(
                "INSERT INTO product_snapshots(id,product_id,version,snapshot_data) VALUES (:snapshot,:id,1,'{}')"
            ),
            [{"snapshot": row["snapshot"], "id": row["id"]} for row in rows],
        )
        await db.execute(
            text("UPDATE products SET latest_snapshot_id=:snapshot WHERE id=:id"),
            [{"snapshot": row["snapshot"], "id": row["id"]} for row in rows],
        )
    return [row["id"] for row in rows]


async def repair(session: AsyncSession) -> datetime:
    await StatisticsCommand.enqueue_recent(
        session, ProductTypes.EnqueueRecentCommand(days=1, now=NOW)
    )
    requested_at = await session.scalar(text("SELECT transaction_timestamp()"))
    assert isinstance(requested_at, datetime)
    return requested_at


async def test_concurrent_repairs_coalesce_across_500_keys(db: AsyncSession) -> None:
    await seed_products(db, 251)
    first_time, second_time = await run_blocked(db, repair, repair)
    assert second_time is not None and second_time > first_time
    rows = (
        await db.execute(text("SELECT day,requested_at FROM product_stats_dirty_days"))
    ).all()
    assert len(rows) == 502
    assert {row.day for row in rows} == {TODAY, TODAY - timedelta(days=1)}
    assert {row.requested_at for row in rows} == {second_time}


@pytest.mark.parametrize("worker_outcome", ["commit", "rollback"])
async def test_repair_waits_for_worker_and_preserves_new_request(
    db: AsyncSession, worker_outcome: Literal["commit", "rollback"]
) -> None:
    product = (await seed_products(db))[0]
    await QueueCommand.mark_statistics_dirty(
        db, ProductTypes.MarkStatisticsDirtyCommand(product, NOW)
    )

    async def worker(session: AsyncSession) -> ProductTypes.StatisticsWorkInfo:
        work = await StatisticsCommand.claim_statistics_work(session)
        assert work is not None and (work.product_id, work.day) == (product, TODAY)
        async with AsyncSession(db.bind) as other:
            async with use_case_transaction(other):
                await prepare_connection(other)
                assert await StatisticsCommand.claim_statistics_work(other) is None
        await StatisticsCommand.complete_statistics_work(
            session, ProductTypes.RebuildDayCommand(product_id=product, day=TODAY)
        )
        return work

    _, requested_at = await run_blocked(
        db, worker, repair, rollback_first=worker_outcome == "rollback"
    )
    rows = (
        await db.execute(text("SELECT day,requested_at FROM product_stats_dirty_days"))
    ).all()
    assert len(rows) == 2
    assert {row.day for row in rows} == {TODAY, TODAY - timedelta(days=1)}
    assert {row.requested_at for row in rows} == {requested_at}


async def test_dirty_request_waits_for_repair_then_refreshes_timestamp(
    db: AsyncSession,
) -> None:
    product = (await seed_products(db))[0]

    async def mark(session: AsyncSession) -> datetime:
        # Both uncommitted repair rows are skipped by another worker.
        async with AsyncSession(db.bind) as other:
            async with use_case_transaction(other):
                await prepare_connection(other)
                assert await StatisticsCommand.claim_statistics_work(other) is None
        await QueueCommand.mark_statistics_dirty(
            session, ProductTypes.MarkStatisticsDirtyCommand(product, NOW)
        )
        instant = await session.scalar(text("SELECT transaction_timestamp()"))
        assert isinstance(instant, datetime)
        return instant

    repair_at, dirty_at = await run_blocked(db, repair, mark)
    rows = dict(
        (
            await db.execute(
                text("SELECT day,requested_at FROM product_stats_dirty_days")
            )
        )
        .tuples()
        .all()
    )
    assert rows == {TODAY: dirty_at, TODAY - timedelta(days=1): repair_at}
    await db.rollback()
    async with use_case_transaction(db):
        for _ in range(2):
            work = await StatisticsCommand.claim_statistics_work(db)
            assert work is not None
            await StatisticsCommand.complete_statistics_work(
                db,
                ProductTypes.RebuildDayCommand(
                    product_id=work.product_id, day=work.day
                ),
            )
        assert await StatisticsCommand.claim_statistics_work(db) is None
