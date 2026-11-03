"""Real UNIQUE/row-lock cycle control and nonblocking admin fencing on PostgreSQL."""

import asyncio

import pytest
from sqlalchemy import ScalarResult, Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_u25_postgres_concurrency import (
    prepare_connection,
    seed_admin,
    wait_for_blocker,
)

from app.db.models.tag import Tag
from app.db.transaction import use_case_transaction
from app.modules.content.tag import repository as Repository
from app.modules.content.tag import types as Types
from app.modules.content.tag.service import command as Command

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("fenced", [False, True])
@pytest.mark.parametrize("count", [2, 501])
@pytest.mark.parametrize("operation", ["resolve", "acquire", "create_then_resolve"])
async def test_prelocked_beta_rename_and_alpha_acquisition(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    fenced: bool,
    count: int,
    operation: str,
) -> None:
    actor = await seed_admin(db)
    beta = (await Command.resolve_tags(db, Types.ResolveTagsCommand(("beta",))))[0]
    names = ("alpha", *(f"alpha-{n:04}" for n in range(count - 2)), "beta")
    locked, inserted, release_select = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids: dict[str, int] = {}
    if not fenced:

        async def prior_lock(session: AsyncSession) -> None:
            pass  # Explicit old-order control; only the new fence is disabled.

        monkeypatch.setattr(Repository, "lock_dictionary_for_update", prior_lock)
    async with (
        AsyncSession(db.bind, expire_on_commit=False) as resolver,
        AsyncSession(db.bind, expire_on_commit=False) as admin,
    ):
        scalars = resolver.scalars

        async def pause_select(statement: Select[tuple[Tag]]) -> ScalarResult[Tag]:
            inserted.set()
            await release_select.wait()
            return await scalars(statement)

        monkeypatch.setattr(resolver, "scalars", pause_select)

        async def acquire() -> object:
            await locked.wait()
            async with use_case_transaction(resolver):
                pids["resolver"] = await prepare_connection(resolver)
                if operation == "create_then_resolve":
                    await Command.create_tag(
                        resolver, Types.CreateTagCommand(actor, "alpha")
                    )
                if operation == "acquire":
                    return await Command.acquire_tag_names(
                        resolver, Types.AcquireTagNamesCommand(names)
                    )
                return await Command.resolve_tags(
                    resolver, Types.ResolveTagsCommand(names)
                )

        async def rename() -> Types.TagInfo:
            async with use_case_transaction(admin):
                pids["admin"] = await prepare_connection(admin)
                # A caller can already hold this lock before entering the service.
                await Repository.get_tag(admin, beta.id, exclusive=True)
                await admin.execute(
                    text("INSERT INTO tags(name) VALUES ('outer-write')")
                )
                locked.set()
                await inserted.wait()
                return await Command.update_tag(
                    admin, Types.UpdateTagCommand(beta.id, actor, "alpha")
                )

        tasks = [asyncio.create_task(acquire()), asyncio.create_task(rename())]
        try:
            await asyncio.wait_for(inserted.wait(), 5)
            if fenced:
                with pytest.raises(
                    ValueError, match="Tag dictionary is busy"
                ) as conflict:
                    await asyncio.wait_for(asyncio.shield(tasks[1]), 5)
                assert (
                    getattr(conflict.value.__cause__.orig, "sqlstate", None) == "55P03"
                )
            else:
                await wait_for_blocker(db, pids["resolver"], pids["admin"])
            release_select.set()
            outcomes = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), 15
            )
        finally:
            release_select.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    states = [
        getattr(getattr(item, "orig", None), "sqlstate", None) for item in outcomes
    ]
    if fenced:
        assert not isinstance(outcomes[0], BaseException)
        assert isinstance(outcomes[1], ValueError)
        async with db.begin():
            assert set(await db.scalars(select(Tag.name))) == set(names)
            assert await db.scalar(select(Tag.name).where(Tag.id == beta.id)) == "beta"
    else:
        assert states.count("40P01") == 1
    print(f"fenced={fenced} count={count} operation={operation} sqlstates={states}")


@pytest.mark.parametrize("action", ["update", "deactivate"])
async def test_caught_admin_fence_conflict_rolls_back_entire_outer_transaction(
    db: AsyncSession,
    action: str,
) -> None:
    actor = await seed_admin(db)
    tag = (await Command.resolve_tags(db, Types.ResolveTagsCommand(("beta",))))[0]
    async with AsyncSession(db.bind, expire_on_commit=False) as resolver:
        async with use_case_transaction(resolver):
            await Command.resolve_tags(
                resolver, Types.ResolveTagsCommand(("alpha", "beta"))
            )
            # No service retries or reuses the transaction aborted by NOWAIT.
            with pytest.raises(RuntimeError, match="nested use case failed"):
                async with use_case_transaction(db):
                    await db.execute(
                        text("INSERT INTO tags(name) VALUES ('outer-write')")
                    )
                    with pytest.raises(ValueError, match="Tag dictionary is busy"):
                        if action == "update":
                            await Command.update_tag(
                                db, Types.UpdateTagCommand(tag.id, actor, "alpha")
                            )
                        else:
                            await Command.deactivate_tag(
                                db, Types.DeactivateTagCommand(tag.id, actor)
                            )
    async with db.begin():
        assert set(await db.scalars(select(Tag.name))) == {"alpha", "beta"}
        assert await db.scalar(select(Tag.is_active).where(Tag.id == tag.id)) is True
    assert db.bind.pool.checkedout() == 0


async def test_admin_rename_preserves_exact_unique_conflict(db: AsyncSession) -> None:
    actor = await seed_admin(db)
    beta, _ = await Command.resolve_tags(
        db, Types.ResolveTagsCommand(("beta", "alpha"))
    )
    with pytest.raises(ValueError, match="Tag name already exists") as caught:
        await Command.update_tag(db, Types.UpdateTagCommand(beta.id, actor, " alpha "))
    assert getattr(caught.value.__cause__.orig, "sqlstate", None) == "23505"
    async with db.begin():
        assert set(await db.scalars(select(Tag.name))) == {"alpha", "beta"}
