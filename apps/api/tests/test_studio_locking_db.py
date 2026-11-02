"""Studio lock ordering, CAS and retries on independent PostgreSQL connections."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.models.lorebook import Lorebook
from app.db.models.product import ProductLorebook, ProductStudioDraft
from app.db.transaction import use_case_transaction
from app.modules.content.product import types as Types
from app.modules.content.product.service.command import studio as StudioCommand
from app.modules.content.product.service.query import studio as StudioQuery
from app.use_cases import studio_components as Components

pytestmark = pytest.mark.asyncio
Save = Callable[
    [AsyncSession, Types.SaveStudioDraftCommand], Awaitable[Types.StudioDraftInfo]
]
Outcome = Types.StudioDraftInfo | Types.StudioDraftConflictError


def document(
    title: str = "Original", tags: tuple[str, ...] = ()
) -> Types.ProductJsonObject:
    return {
        "version": 2,
        "work": {
            "title": title,
            "introduction": "",
            "visibility": "비공개",
            "defaultSceneId": "",
            "tags": list(tags),
        },
        "characters": [],
        "lorebooks": [],
        "scenes": [],
    }


async def seed_owner(db: AsyncSession) -> UUID:
    owner_id = uuid4()
    async with use_case_transaction(db):
        await db.execute(
            text("INSERT INTO users(id,email) VALUES (:id,:email)"),
            {"id": owner_id, "email": f"{owner_id}@studio.test"},
        )
    return owner_id


async def seed_draft(db: AsyncSession) -> tuple[UUID, Types.StudioDraftInfo]:
    owner_id = await seed_owner(db)
    draft = await Components.save_studio(
        db, Types.SaveStudioDraftCommand(uuid4(), owner_id, None, document())
    )
    return owner_id, draft


async def wait_for_advisory_wait(
    db: AsyncSession, leader_pid: int, follower_pid: int
) -> None:
    """Observe a real lock wait, rather than assuming a task switch took place."""
    async with AsyncSession(db.bind) as observer:
        async with asyncio.timeout(5):
            while not await observer.scalar(
                text(
                    "SELECT :leader = ANY(pg_blocking_pids(:follower)) "
                    "AND EXISTS (SELECT 1 FROM pg_locks "
                    "WHERE pid=:follower AND locktype='advisory' AND NOT granted)"
                ),
                {"leader": leader_pid, "follower": follower_pid},
            ):
                await asyncio.sleep(0.01)


async def race_saves(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    first_save: Save,
    first_command: Types.SaveStudioDraftCommand,
    second_save: Save,
    second_command: Types.SaveStudioDraftCommand,
) -> tuple[Outcome, Outcome]:
    """Hold the first advisory lock until PG confirms the other connection waits.

    With the former inverted order the second revision save holds the product row
    while waiting here; releasing the first task then produces a real deadlock.
    The wrapper only places barriers around the production PostgreSQL lock call.
    """
    first_locked, release_first, second_attempted = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    pids: dict[str, int] = {}

    async def gated_lock(session: AsyncSession, namespace: str, key: str) -> None:
        role = session.info["studio_test_role"]
        if role == "second":
            second_attempted.set()
        await lock_key(session, namespace, key)
        if role == "first" and not first_locked.is_set():
            first_locked.set()
            await release_first.wait()

    monkeypatch.setattr(StudioCommand, "lock_key", gated_lock)
    monkeypatch.setattr(StudioQuery, "lock_key", gated_lock)

    async def run_save(
        role: str, save: Save, command: Types.SaveStudioDraftCommand
    ) -> Outcome:
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            session.info["studio_test_role"] = role
            try:
                async with use_case_transaction(session):
                    await session.execute(text("SET LOCAL statement_timeout = '8s'"))
                    await session.execute(text("SET LOCAL lock_timeout = '6s'"))
                    pid = await session.scalar(text("SELECT pg_backend_pid()"))
                    assert isinstance(pid, int)
                    pids[role] = pid
                    return await save(session, command)
            except Types.StudioDraftConflictError as error:
                return error

    tasks: list[asyncio.Task[Outcome]] = []
    try:
        async with asyncio.timeout(15):
            tasks.append(
                asyncio.create_task(run_save("first", first_save, first_command))
            )
            await first_locked.wait()
            tasks.append(
                asyncio.create_task(run_save("second", second_save, second_command))
            )
            await second_attempted.wait()
            assert pids["first"] != pids["second"]
            await wait_for_advisory_wait(db, pids["first"], pids["second"])
            release_first.set()
            first, second = await asyncio.gather(*tasks)
            return first, second
    finally:
        release_first.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("direct_first", [True, False])
async def test_revision_edit_crosses_revisionless_same_content_retry(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, direct_first: bool
) -> None:
    owner, original = await seed_draft(db)
    edit = Types.SaveStudioDraftCommand(
        original.product_id, owner, 1, document("Edited")
    )
    retry = Types.SaveStudioDraftCommand(
        original.product_id,
        owner,
        None,
        document() if direct_first else document("Edited"),
    )
    direct = (StudioCommand.save_studio_draft, retry)
    composed = (Components.save_studio, edit)
    first, second = await race_saves(
        db,
        monkeypatch,
        *(direct if direct_first else composed),
        *(composed if direct_first else direct),
    )
    assert isinstance(first, Types.StudioDraftInfo)
    assert isinstance(second, Types.StudioDraftInfo)
    assert (first.revision, second.revision) == ((1, 2) if direct_first else (2, 2))
    stored = await StudioQuery.get_studio_draft(
        db, Types.GetStudioDraftCommand(original.product_id, owner)
    )
    assert stored.revision == 2 and stored.document == document("Edited")
    assert stored.content_digest == second.content_digest
    if not direct_first:
        assert first == second  # Retry did not change updated_at or receipt metadata.


@pytest.mark.parametrize("direct_first", [True, False])
async def test_same_revision_different_documents_has_one_winner(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, direct_first: bool
) -> None:
    owner, original = await seed_draft(db)
    first_save, second_save = (
        (StudioCommand.save_studio_draft, Components.save_studio)
        if direct_first
        else (Components.save_studio, StudioCommand.save_studio_draft)
    )
    first, second = await race_saves(
        db,
        monkeypatch,
        first_save,
        Types.SaveStudioDraftCommand(original.product_id, owner, 1, document("Winner")),
        second_save,
        Types.SaveStudioDraftCommand(original.product_id, owner, 1, document("Loser")),
    )
    assert isinstance(first, Types.StudioDraftInfo) and first.revision == 2
    assert isinstance(second, Types.StudioDraftConflictError)
    stored = await StudioQuery.get_studio_draft(
        db, Types.GetStudioDraftCommand(original.product_id, owner)
    )
    assert stored == first
    assert (
        await db.scalar(
            text("SELECT title FROM products WHERE id=:id"), {"id": original.product_id}
        )
        == "Winner"
    )


async def test_previous_product_first_order_reproduces_postgres_deadlock(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, original = await seed_draft(db)

    async def legacy_save(
        session: AsyncSession, command: Types.SaveStudioDraftCommand
    ) -> Types.StudioDraftInfo:
        # Negative control: reproduce the former publication-read locks before
        # entering the unchanged advisory-taking save. All locks are real SQL.
        await StudioQuery.QueryService.get_owned_product(
            session,
            Types.OwnedProductCommand(command.product_id, command.owner_id, lock=True),
        )
        await StudioCommand.Repository.get_studio_draft(
            session, command.product_id, lock=True
        )
        return await StudioCommand.save_studio_draft(session, command)

    with pytest.raises(DBAPIError) as caught:
        await race_saves(
            db,
            monkeypatch,
            StudioCommand.save_studio_draft,
            Types.SaveStudioDraftCommand(original.product_id, owner, None, document()),
            legacy_save,
            Types.SaveStudioDraftCommand(
                original.product_id, owner, 1, document("Edited")
            ),
        )
    assert getattr(caught.value.orig, "sqlstate", None) == "40P01"


async def test_concurrent_same_revision_same_document_reuses_winning_result(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, original = await seed_draft(db)
    command = Types.SaveStudioDraftCommand(
        original.product_id, owner, 1, document("Edited")
    )
    first, second = await race_saves(
        db,
        monkeypatch,
        Components.save_studio,
        command,
        StudioCommand.save_studio_draft,
        command,
    )
    assert isinstance(first, Types.StudioDraftInfo) and first.revision == 2
    assert first == second


async def test_concurrent_same_document_creation_reuses_product_and_draft(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_owner(db)
    command = Types.SaveStudioDraftCommand(uuid4(), owner, None, document())
    first, second = await race_saves(
        db,
        monkeypatch,
        StudioCommand.save_studio_draft,
        command,
        Components.save_studio,
        command,
    )
    assert isinstance(first, Types.StudioDraftInfo) and first.revision == 1
    assert first == second
    assert await db.scalar(text("SELECT count(*) FROM products")) == 1
    assert await db.scalar(text("SELECT count(*) FROM product_studio_drafts")) == 1


@pytest.mark.parametrize("expected_revision", [None, 1, 2])
async def test_same_content_retry_keeps_saved_revision_digest_receipt_and_timestamp(
    db: AsyncSession, expected_revision: int | None
) -> None:
    owner, original = await seed_draft(db)
    changed = await Components.save_studio(
        db,
        Types.SaveStudioDraftCommand(original.product_id, owner, 1, document("Edited")),
    )
    mapping: Types.ProductJsonObject = {"characters": {}, "entries": {}, "receipts": {}}
    release = Types.ReleaseInfo(uuid4(), 1, "First", "Body", "initial", "choice")
    await StudioCommand.mark_studio_publication(
        db,
        Types.MarkStudioPublicationCommand(
            original.product_id, owner, changed.content_digest, release, mapping
        ),
    )
    before = await StudioQuery.get_studio_draft(
        db, Types.GetStudioDraftCommand(original.product_id, owner)
    )
    await db.rollback()
    for save in (StudioCommand.save_studio_draft, Components.save_studio):
        retried = await save(
            db,
            Types.SaveStudioDraftCommand(
                original.product_id, owner, expected_revision, document("Edited")
            ),
        )
        assert retried == before


async def test_cas_conflict_rolls_back_real_legacy_mapping_adoption(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, original = await seed_draft(db)
    legacy: Types.ProductJsonObject = {"snapshot_id": str(uuid4()), "version": 1}
    async with use_case_transaction(db):
        book = Lorebook(id=uuid4(), owner_id=owner, title="Legacy")
        db.add(book)
        await db.flush()
        db.add(ProductLorebook(product_id=original.product_id, lorebook_id=book.id))
        row = await db.get(ProductStudioDraft, original.product_id)
        assert row is not None
        row.publication_release = legacy
        row.publication_digest = original.content_digest
    adopted: list[Types.StudioDraftInfo] = []
    set_components = StudioCommand.set_studio_components

    async def observe_adoption(
        session: AsyncSession, command: Types.SetStudioComponentsCommand
    ) -> Types.StudioDraftInfo:
        info = await set_components(session, command)
        adopted.append(info)
        return info

    monkeypatch.setattr(StudioCommand, "set_studio_components", observe_adoption)
    with pytest.raises(Types.StudioDraftConflictError):
        await Components.save_studio(
            db,
            Types.SaveStudioDraftCommand(
                original.product_id, owner, 99, document("Stale")
            ),
        )
    assert len(adopted) == 1 and adopted[0].publication_release is not None
    assert "_studio" in adopted[0].publication_release
    stored = await StudioQuery.get_studio_draft(
        db, Types.GetStudioDraftCommand(original.product_id, owner)
    )
    assert stored.revision == 1 and stored.document == original.document
    assert stored.publication_release == legacy
    await db.rollback()
    # A separate connection can immediately save after the failed transaction.
    async with AsyncSession(db.bind) as session:
        saved = await Components.save_studio(
            session,
            Types.SaveStudioDraftCommand(
                original.product_id, owner, 1, document("Valid")
            ),
        )
    assert (
        saved.revision == 2
        and saved.publication_release == adopted[0].publication_release
    )


async def test_failure_after_draft_flush_rolls_back_profile_tags_and_document(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, original = await seed_draft(db)
    save_draft = StudioCommand.Repository.save_studio_draft

    async def fail_after_flush(
        session: AsyncSession,
        product_id: UUID,
        revision: int,
        digest: str,
        value: Types.ProductJsonObject,
        existing: ProductStudioDraft | None,
    ) -> ProductStudioDraft:
        row = await save_draft(session, product_id, revision, digest, value, existing)
        assert row.revision == 2
        assert await session.scalar(text("SELECT count(*) FROM product_tags")) == 1
        raise RuntimeError("Failure after draft flush")

    monkeypatch.setattr(StudioCommand.Repository, "save_studio_draft", fail_after_flush)
    with pytest.raises(RuntimeError, match="after draft flush"):
        await Components.save_studio(
            db,
            Types.SaveStudioDraftCommand(
                original.product_id, owner, 1, document("Failed", ("new tag",))
            ),
        )
    stored = await StudioQuery.get_studio_draft(
        db, Types.GetStudioDraftCommand(original.product_id, owner)
    )
    assert stored == original
    assert (
        await db.scalar(
            text("SELECT title FROM products WHERE id=:id"), {"id": original.product_id}
        )
        == "Original"
    )
    assert await db.scalar(text("SELECT count(*) FROM product_tags")) == 0
    assert await db.scalar(text("SELECT count(*) FROM tags")) == 0
