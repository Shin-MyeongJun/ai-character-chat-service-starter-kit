"""Studio HTTP publication, real PG lock ordering and durable replay receipts."""

import asyncio
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_integration import ready_product
from test_studio_publication import document
from test_u25_postgres_concurrency import seed_admin, wait_for_blocker

from app.db.models.product import ProductStudioDraft
from app.db.models.snapshot.product import ProductSnapshot
from app.db.models.tag import Tag
from app.db.transaction import use_case_transaction
from app.http import dependencies, studio_publication
from app.modules.content.product import types as ProductTypes
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommand
from app.use_cases import studio_publication as Publication
from app.use_cases.studio_components import StudioMapping

pytestmark = pytest.mark.asyncio


def http_app(db: AsyncSession, owner: UUID) -> FastAPI:
    app = FastAPI()
    app.include_router(studio_publication.router)

    async def session() -> AsyncIterator[AsyncSession]:
        # Unbound sessions also support offline public-service contract tests.
        async with AsyncSession(
            getattr(db, "bind", None), expire_on_commit=False
        ) as value:
            yield value

    app.dependency_overrides[dependencies.get_product_session] = session
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner
    return app


async def save(
    client: httpx.AsyncClient,
    product: UUID,
    revision: int | None,
    value: ProductTypes.ProductJsonObject,
) -> int:
    response = await client.put(
        f"/products/{product}/studio-draft",
        json={"expected_revision": revision, "document": value},
    )
    assert response.status_code == 200
    result = response.json()["revision"]
    assert isinstance(result, int)
    return result


def request(revision: int, model: UUID) -> dict[str, object]:
    return {
        "expected_revision": revision,
        "model_id": str(model),
        "reasoning_effort": "low",
        "summary": "Studio",
        "body": "Studio release",
    }


@pytest.mark.parametrize(
    ("ordered", "preexisting"), [(False, False), (True, False), (True, True)]
)
async def test_cross_component_publications_use_one_dictionary_order(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, ordered: bool, preexisting: bool
) -> None:
    """The old-order control must emit 40P01; the fix must wait then publish both."""
    owner, _, _, _, model, _ = await ready_product(db)
    names = ("studio-alpha", "studio-beta")
    if preexisting:
        await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(names))
    barrier = asyncio.Barrier(2)
    shared_barrier = asyncio.Barrier(2)
    pids: set[int] = set()
    first_pid: int | None = None
    sqlstates: list[str] = []
    acquire, resolve = TagCommand.acquire_tag_names, TagCommand.resolve_tags

    async def identify(session: AsyncSession) -> int:
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        await session.execute(text("SET LOCAL lock_timeout = '8s'"))
        pid = await session.scalar(text("SELECT pg_backend_pid()"))
        assert isinstance(pid, int)
        pids.add(pid)
        return pid

    async def acquire_names(
        session: AsyncSession, command: TagTypes.AcquireTagNamesCommand
    ) -> None:
        nonlocal first_pid
        if not ordered:
            return  # Explicit prior-order control, never used by production.
        pid = await identify(session)
        await asyncio.wait_for(barrier.wait(), 5)
        await acquire(session, command)
        if preexisting:
            # Existing names retain compatible SHARE locks in both transactions.
            await asyncio.wait_for(shared_barrier.wait(), 5)
        elif first_pid is None:
            first_pid = pid
            assert len(pids) == 2
            await wait_for_blocker(
                db, pid, next(value for value in pids if value != pid)
            )

    async def resolve_names(
        session: AsyncSession, command: TagTypes.ResolveTagsCommand
    ) -> tuple[TagTypes.TagInfo, ...]:
        tags = await resolve(session, command)
        if not ordered and not session.info.get("studio_first_tag"):
            session.info["studio_first_tag"] = True
            await identify(session)
            await asyncio.wait_for(barrier.wait(), 5)
        return tags

    def on_error(context: object) -> None:
        state = getattr(getattr(context, "original_exception", None), "sqlstate", None)
        if isinstance(state, str):
            sqlstates.append(state)

    app = http_app(db, owner.id)
    assert db.bind is not None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://studio.test",
    ) as client:
        products = [uuid4(), uuid4()]
        revisions = []
        for product, pair in zip(products, (names, names[::-1]), strict=True):
            value = document()
            value["characters"][0]["tags"] = [pair[0]]
            value["lorebooks"][0]["tags"] = [pair[1]]
            revisions.append(await save(client, product, None, value))
        with monkeypatch.context() as patch:
            patch.setattr(TagCommand, "acquire_tag_names", acquire_names)
            patch.setattr(TagCommand, "resolve_tags", resolve_names)
            event.listen(db.bind.sync_engine, "handle_error", on_error)
            tasks = [
                asyncio.create_task(
                    client.post(
                        f"/products/{product}/studio-publication",
                        json=request(revision, model.id),
                    )
                )
                for product, revision in zip(products, revisions, strict=True)
            ]
            try:
                responses = await asyncio.wait_for(asyncio.gather(*tasks), 20)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                event.remove(db.bind.sync_engine, "handle_error", on_error)
        statuses = sorted(response.status_code for response in responses)
        assert len(pids) == 2
        assert statuses == ([200, 200] if ordered else [200, 500])
        assert ("40P01" in sqlstates) is (not ordered)
        async with db.begin():
            assert await db.scalar(
                select(func.count()).select_from(ProductSnapshot)
            ) == (2 if ordered else 1)
        for product, revision in zip(products, revisions, strict=True):
            replay = await client.post(
                f"/products/{product}/studio-publication",
                json=request(revision, model.id),
            )
            assert replay.status_code == 200
        async with db.begin():
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 2
            )
            assert await db.scalar(select(func.count()).select_from(Tag)) == 2
        print(
            f"ordered={ordered} preexisting={preexisting} connections=2 statuses={statuses} sqlstates={sqlstates} retry_snapshots=2"
        )


async def test_noop_receipt_survives_draft_save_without_snapshot_or_revision_growth(
    db: AsyncSession,
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product = uuid4()
    value, edited = document(), document()
    edited["work"]["title"] = "Edited"
    app = http_app(db, owner.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://studio.test"
    ) as client:
        revision = await save(client, product, None, value)
        url = f"/products/{product}/studio-publication"
        initial_request = request(revision, model.id)
        first = await client.post(url, json=initial_request)
        assert first.status_code == 200
        async with db.begin():
            snapshot = deepcopy(await db.scalar(select(ProductSnapshot.snapshot_data)))
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None
            original = deepcopy(draft.publication_release)
        revision = await save(client, product, revision, edited)
        revision = await save(client, product, revision, value)
        accepted_request = request(revision, model.id)
        accepted = await client.post(url, json=accepted_request)
        assert accepted.status_code == 200 and accepted.json() == first.json()
        conflict = await client.post(url, json={**accepted_request, "summary": "Other"})
        assert conflict.status_code == 409
        async with db.begin():
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None and draft.revision == revision == 3
            assert draft.document == value
            assert draft.publication_release is not None and original is not None
            # These JSON members were written by the real studio service above.
            mapping = cast(
                StudioMapping, deepcopy(draft.publication_release["_studio"])
            )
            original_mapping = cast(StudioMapping, original["_studio"])
            assert mapping["characters"] == original_mapping["characters"]
            assert mapping["entries"] == original_mapping["entries"]
            assert mapping["book_id"] == original_mapping["book_id"]
            assert mapping["receipts"]["1"] == original_mapping["receipts"]["1"]
            assert (
                mapping["receipts"]["3"]["release"]
                == mapping["receipts"]["1"]["release"]
            )
        await save(client, product, revision, edited)
        for replay_request in (accepted_request, initial_request):
            replay = await client.post(url, json=replay_request)
            assert replay.status_code == 200 and replay.json() == first.json()
        async with db.begin():
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert (
                draft is not None and draft.revision == 4 and draft.document == edited
            )
            assert draft.publication_release is not None
            assert draft.publication_release["_studio"] == mapping
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 1
            )
            assert await db.scalar(select(ProductSnapshot.snapshot_data)) == snapshot


@pytest.mark.parametrize("action", ["rename", "deactivate"])
async def test_whole_publication_acquisition_fences_admin_changes(
    db: AsyncSession, action: str
) -> None:
    actor = await seed_admin(db)
    tag = (await TagCommand.resolve_tags(db, TagTypes.ResolveTagsCommand(("old",))))[0]

    async def acquire_names(session: AsyncSession) -> None:
        await TagCommand.acquire_tag_names(
            session, TagTypes.AcquireTagNamesCommand(names=("new", "old"))
        )

    async def change_tag(session: AsyncSession) -> TagTypes.TagInfo:
        if action == "rename":
            return await TagCommand.update_tag(
                session, TagTypes.UpdateTagCommand(tag.id, actor, "renamed", "edited")
            )
        return await TagCommand.deactivate_tag(
            session, TagTypes.DeactivateTagCommand(tag.id, actor)
        )

    async with AsyncSession(db.bind, expire_on_commit=False) as resolver:
        async with use_case_transaction(resolver):
            await acquire_names(resolver)
            with pytest.raises(ValueError, match="Tag dictionary is busy"):
                await asyncio.wait_for(change_tag(db), 5)


async def test_publication_failure_rolls_back_acquired_names_then_retries(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product = uuid4()
    value = document()
    value["characters"][0]["tags"] = ["rollback-new"]
    app = http_app(db, owner.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://studio.test",
    ) as client:
        revision = await save(client, product, None, value)
        url = f"/products/{product}/studio-publication"
        mark = Publication.mark_studio_publication

        async def fail_after_receipt(
            session: AsyncSession, command: ProductTypes.MarkStudioPublicationCommand
        ) -> ProductTypes.ReleaseInfo:
            await mark(session, command)
            raise ValueError("injected after persisted receipt")

        with monkeypatch.context() as patch:
            patch.setattr(Publication, "mark_studio_publication", fail_after_receipt)
            failed = await client.post(url, json=request(revision, model.id))
            assert failed.status_code == 422
        async with db.begin():
            assert await db.scalar(select(func.count()).select_from(Tag)) == 0
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 0
            )
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None and draft.revision == revision
            assert draft.publication_release is None
        for _ in range(2):
            replay = await client.post(url, json=request(revision, model.id))
            assert replay.status_code == 200
        async with db.begin():
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 1
            )
            assert await db.scalar(select(func.count()).select_from(Tag)) == 1


@pytest.mark.parametrize("new_target", ["character", "lorebook", "work"])
async def test_acquired_inactive_name_is_retained_only_by_its_existing_parent(
    db: AsyncSession, new_target: str
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    actor = await seed_admin(db)
    product = uuid4()
    value = document()
    value["characters"][0]["tags"] = ["retained"]
    app = http_app(db, owner.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://studio.test"
    ) as client:
        revision = await save(client, product, None, value)
        url = f"/products/{product}/studio-publication"
        assert (
            await client.post(url, json=request(revision, model.id))
        ).status_code == 200
        tag = (
            await TagCommand.resolve_tags(
                db, TagTypes.ResolveTagsCommand(("retained",))
            )
        )[0]
        await TagCommand.deactivate_tag(
            db, TagTypes.DeactivateTagCommand(tag.id, actor)
        )
        value["work"]["title"] = "Changed but retaining inactive character tag"
        revision = await save(client, product, revision, value)
        assert (
            await client.post(url, json=request(revision, model.id))
        ).status_code == 200
        if new_target == "character":
            value["characters"].append(
                {
                    "id": "second",
                    "name": "Second",
                    "persona": "Persona",
                    "assets": [],
                    "tags": ["retained"],
                }
            )
        elif new_target == "lorebook":
            value["lorebooks"][0]["tags"] = ["retained"]
        else:
            value["work"]["tags"] = ["retained"]
        revision = await save(client, product, revision, value)
        rejected = await client.post(url, json=request(revision, model.id))
        assert rejected.status_code == 422
        assert "Inactive tags" in rejected.text
        async with db.begin():
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 2
            )
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None and draft.publication_release is not None
            mapping = cast(StudioMapping, draft.publication_release["_studio"])
            assert str(revision) not in mapping["receipts"]


async def test_legacy_snapshot_reuse_adopts_existing_mapping_and_records_receipt(
    db: AsyncSession,
) -> None:
    owner, _, _, _, model, _ = await ready_product(db)
    product = uuid4()
    app = http_app(db, owner.id)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://studio.test"
    ) as client:
        revision = await save(client, product, None, document())
        url = f"/products/{product}/studio-publication"
        accepted_request = request(revision, model.id)
        first = await client.post(url, json=accepted_request)
        assert first.status_code == 200
        async with use_case_transaction(db):
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None and draft.publication_release is not None
            original = deepcopy(draft.publication_release)
            draft.publication_release = {
                key: value for key, value in original.items() if key != "_studio"
            }
        replay = await client.post(url, json=accepted_request)
        assert replay.status_code == 200 and replay.json() == first.json()
        async with db.begin():
            draft = await db.get(ProductStudioDraft, product, populate_existing=True)
            assert draft is not None and draft.publication_release is not None
            mapping = draft.publication_release["_studio"]
            assert mapping == original["_studio"]
            assert draft.revision == revision
            assert (
                await db.scalar(select(func.count()).select_from(ProductSnapshot)) == 1
            )
