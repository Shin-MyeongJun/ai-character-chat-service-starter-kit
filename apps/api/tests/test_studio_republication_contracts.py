"""Follow-up studio publication contracts with public-service doubles."""

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from test_studio_publication_db import http_app, request

from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.product import types as Types
from app.use_cases import studio_publication as Publication


@dataclass
class Backend:
    draft: Types.StudioDraftInfo
    command: Publication.PublishStudioCommand
    book: LoreTypes.LorebookInfo
    character_id: UUID
    entry_ids: dict[str, UUID]
    release: Types.ReleaseInfo
    operations: dict[str, AsyncMock]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> Backend:
    now = datetime.now(UTC)
    product_id, owner_id, character_id, book_id = (uuid4() for _ in range(4))
    old_snapshot, new_snapshot = uuid4(), uuid4()
    entries = {key: uuid4() for key in ("world_rules", "lore:world", "scene:scene")}
    draft = Types.StudioDraftInfo(
        product_id=product_id,
        revision=2,
        content_digest="new-content",
        updated_at=now,
        document={
            "version": 2,
            "work": {
                "title": "Changed story",
                "introduction": "Intro",
                "visibility": "전체 공개",
                "defaultSceneId": "scene",
                "worldRules": "New rules",
                "tags": ["work-tag"],
            },
            "characters": [
                {"id": "hero", "name": "Hero", "persona": "New persona", "assets": []}
            ],
            "lorebooks": [
                {
                    "id": "world",
                    "title": "New world",
                    "content": "New lore",
                    "activation": "always",
                    "tags": ["first", "second"],
                }
            ],
            "scenes": [
                {
                    "id": "scene",
                    "title": "Start",
                    "opening": "Hello",
                    "characterId": "hero",
                }
            ],
        },
        publication_digest="old-content",
        publication_release={
            "snapshot_id": str(old_snapshot),
            "version": 1,
            "_studio": {
                "characters": {"hero": str(character_id)},
                "book_id": str(book_id),
                "entries": {key: str(value) for key, value in entries.items()},
                "receipts": {
                    "1": {
                        "fingerprint": "old-fingerprint",
                        "release": {
                            "snapshot_id": str(old_snapshot),
                            "version": 1,
                            "summary": "First",
                            "body": "Old release",
                            "change_kind": "initial",
                            "update_policy": "choice",
                        },
                    }
                },
            },
        },
    )
    book = LoreTypes.LorebookInfo(
        book_id, owner_id, "Old title", "Old rules", "unlisted", "approved", now, now
    )
    release = Types.ReleaseInfo(
        new_snapshot, 2, "Second", "New release", "content", "choice"
    )
    operations: dict[str, AsyncMock] = {}

    def patch(module: object, name: str, value: object = None) -> None:
        operation = AsyncMock(return_value=value)
        operations[name] = operation
        monkeypatch.setattr(module, name, operation)

    patch(Publication, "get_studio_draft_for_publication", draft)
    patch(Publication.TagCommandService, "acquire_tag_names")
    patch(Publication.CharacterCommand, "update_character", MagicMock(id=character_id))
    patch(Publication.CharacterCommand, "create_character")
    patch(Publication.CharacterQuery, "list_character_assets", [])
    patch(Publication.CharacterQuery, "get_owned_characters", [])
    patch(Publication.CharacterTags, "replace_public_tags")
    patch(Publication.LoreQuery, "get_owned_lorebooks", [book])
    patch(Publication.LoreCommand, "update_lorebook", book)
    patch(Publication.LoreCommand, "create_lorebook")
    # Distinguish same-named character/lore tag calls in assertions.
    lore_tags = AsyncMock()
    operations["lore_tags"] = lore_tags
    monkeypatch.setattr(Publication.LoreTags, "replace_public_tags", lore_tags)
    patch(Publication.LoreCommand, "update_lorebook_entry")

    async def update_entry(
        session: AsyncSession,
        command: LoreTypes.UpdateLorebookEntryCommand,
    ) -> SimpleNamespace:
        assert session.in_transaction()
        return SimpleNamespace(id=command.entry_id)

    operations["update_lorebook_entry"].side_effect = update_entry
    patch(Publication.LoreCommand, "create_lorebook_entry")
    patch(Publication.LoreCommand, "delete_lorebook_entry")
    patch(Publication.CompositionCommand, "replace_composition")
    patch(Publication.SettingsCommand, "set_settings")
    patch(Publication.ProductCommand, "update_product")
    patch(Publication.ReleasesCommand, "publish_product", release)
    patch(Publication, "mark_studio_publication")
    command = Publication.PublishStudioCommand(
        product_id, owner_id, 2, uuid4(), "low", "Second", "New release"
    )
    patch(
        Publication.ProductQueryService,
        "get_product_snapshot",
        SimpleNamespace(
            snapshot_data={
                "model": {
                    "id": str(command.model_id),
                    "reasoning_effort": command.reasoning_effort,
                }
            }
        ),
    )
    return Backend(draft, command, book, character_id, entries, release, operations)


def track_transactions(session: AsyncSession) -> list[str]:
    events: list[str] = []

    def committed(session: Session) -> None:
        events.append("commit")

    def rolled_back(session: Session) -> None:
        events.append("rollback")

    event.listen(session.sync_session, "after_commit", committed)
    event.listen(session.sync_session, "after_rollback", rolled_back)
    return events


@pytest.mark.asyncio
async def test_follow_up_refreshes_parent_and_tags_reuses_ids_and_keeps_old_receipt(
    backend: Backend,
) -> None:
    item = backend
    original = deepcopy(item.draft.publication_release)
    async with AsyncSession() as session:
        events = track_transactions(session)
        result = await Publication.publish_studio(session, item.command)
    assert result == item.release and events == ["commit"]
    ops = item.operations
    owned = ops["get_owned_lorebooks"].await_args
    assert owned is not None
    assert owned.args[1] == LoreTypes.GetOwnedLorebooksCommand(
        ids=(item.book.id,), owner_id=item.command.owner_id, lock=True
    )
    updated = ops["update_lorebook"].await_args
    assert updated is not None
    assert updated.args[1] == LoreTypes.UpdateLorebookCommand(
        item.book.id,
        item.command.owner_id,
        "Changed story · 스튜디오",
        "New rules",
        "unlisted",
    )
    tags = ops["lore_tags"].await_args
    assert tags is not None
    assert (
        tags.args[1].names == ("first", "second")
        and tags.args[1].target_id == item.book.id
    )
    assert {
        call.args[1].entry_id for call in ops["update_lorebook_entry"].await_args_list
    } == set(item.entry_ids.values())
    character_call = ops["update_character"].await_args
    product_call = ops["update_product"].await_args
    assert character_call is not None and product_call is not None
    assert character_call.args[1].character_id == item.character_id
    assert product_call.args[1].value.visibility == "public"
    ops["create_lorebook"].assert_not_awaited()
    ops["create_character"].assert_not_awaited()
    ops["create_lorebook_entry"].assert_not_awaited()
    mark_call = ops["mark_studio_publication"].await_args
    assert mark_call is not None and original is not None
    marked = mark_call.args[1]
    assert marked.mapping["receipts"]["1"]["fingerprint"] == "old-fingerprint"
    assert (
        marked.mapping["receipts"]["1"]["release"]["snapshot_id"]
        == original["snapshot_id"]
    )
    assert marked.mapping["receipts"]["2"]["release"]["snapshot_id"] == str(
        item.release.snapshot_id
    )
    assert item.draft.publication_release == original


@pytest.mark.asyncio
async def test_removing_rules_and_all_lore_tags_clears_parent_and_old_rule_entry(
    backend: Backend,
) -> None:
    item = backend
    document = deepcopy(item.draft.document)
    # Rebuild the authored values without mutating the saved receipt.
    document["work"] = {
        "title": "Changed story",
        "introduction": "Intro",
        "visibility": "비공개",
        "defaultSceneId": "scene",
        "worldRules": "",
    }
    document["lorebooks"] = []
    item.operations["get_studio_draft_for_publication"].return_value = replace(
        item.draft, document=document
    )
    async with AsyncSession() as session:
        await Publication.publish_studio(session, item.command)
    update_call = item.operations["update_lorebook"].await_args
    tags_call = item.operations["lore_tags"].await_args
    assert update_call is not None and tags_call is not None
    assert update_call.args[1].description is None
    assert tags_call.args[1].names == ()
    deleted = {
        call.args[1].entry_id
        for call in item.operations["delete_lorebook_entry"].await_args_list
    }
    assert deleted == {item.entry_ids["world_rules"], item.entry_ids["lore:world"]}


@pytest.mark.asyncio
async def test_lore_tag_failure_rolls_back_and_does_not_publish_or_record_receipt(
    backend: Backend,
) -> None:
    failure = ValueError("invalid tag")
    backend.operations["lore_tags"].side_effect = failure
    async with AsyncSession() as session:
        events = track_transactions(session)
        with pytest.raises(ValueError) as caught:
            await Publication.publish_studio(session, backend.command)
    assert caught.value is failure and events == ["rollback"]
    backend.operations["publish_product"].assert_not_awaited()
    backend.operations["mark_studio_publication"].assert_not_awaited()


@pytest.mark.asyncio
async def test_lost_response_replays_receipt_after_newer_draft_without_domain_writes(
    backend: Backend,
) -> None:
    item = backend
    async with AsyncSession() as session:
        await Publication.publish_studio(session, item.command)
    mark_call = item.operations["mark_studio_publication"].await_args
    assert mark_call is not None
    marked = mark_call.args[1]
    next_draft = replace(
        item.draft,
        revision=3,
        content_digest="newer-content",
        publication_release={
            "snapshot_id": str(item.release.snapshot_id),
            "_studio": marked.mapping,
        },
    )
    for operation in item.operations.values():
        operation.reset_mock()
    item.operations["get_studio_draft_for_publication"].return_value = next_draft
    async with AsyncSession() as session:
        assert await Publication.publish_studio(session, item.command) == item.release
    for name, operation in item.operations.items():
        if name != "get_studio_draft_for_publication":
            operation.assert_not_awaited()
    async with AsyncSession() as session:
        with pytest.raises(
            Types.StudioDraftConflictError, match="different request parameters"
        ):
            await Publication.publish_studio(
                session, replace(item.command, body="Changed retry")
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("storage_failure", [False, True])
async def test_reused_snapshot_records_current_revision_atomically(
    backend: Backend, storage_failure: bool
) -> None:
    item = backend
    prior = deepcopy(item.draft.publication_release)
    assert prior is not None
    prior.update({**asdict(item.release), "snapshot_id": str(item.release.snapshot_id)})
    item.draft = replace(
        item.draft,
        publication_digest=item.draft.content_digest,
        publication_release=prior,
    )
    item.operations["get_studio_draft_for_publication"].return_value = item.draft
    if storage_failure:
        item.operations["mark_studio_publication"].side_effect = ValueError(
            "receipt write failed"
        )
    async with AsyncSession() as session:
        events = track_transactions(session)
        if storage_failure:
            with pytest.raises(ValueError, match="receipt write failed"):
                await Publication.publish_studio(session, item.command)
            assert events == ["rollback"]
        else:
            assert (
                await Publication.publish_studio(session, item.command) == item.release
            )
            assert events == ["commit"]
    marked_call = item.operations["mark_studio_publication"].await_args
    assert marked_call is not None
    marked = marked_call.args[1]
    assert marked.content_digest == item.draft.content_digest
    assert marked.release == item.release
    prior_mapping = prior["_studio"]
    assert isinstance(prior_mapping, dict)
    prior_receipts = prior_mapping["receipts"]
    assert isinstance(prior_receipts, dict)
    assert marked.mapping["receipts"]["1"] == prior_receipts["1"]
    assert marked.mapping["characters"] == prior_mapping["characters"]
    assert item.draft.publication_release == prior  # no mutation before persistence
    item.operations["publish_product"].assert_not_awaited()
    item.operations["update_character"].assert_not_awaited()
    if storage_failure:
        return
    for operation in item.operations.values():
        operation.reset_mock()
    item.operations["get_studio_draft_for_publication"].return_value = replace(
        item.draft,
        revision=3,
        content_digest="next-edit",
        publication_release={**prior, "_studio": marked.mapping},
    )
    async with AsyncSession() as session:
        assert await Publication.publish_studio(session, item.command) == item.release
        with pytest.raises(Types.StudioDraftConflictError, match="different request"):
            await Publication.publish_studio(
                session, replace(item.command, summary="Other")
            )
    item.operations["mark_studio_publication"].assert_not_awaited()


@pytest.mark.asyncio
async def test_all_tag_names_are_acquired_after_parent_locks_before_component_writes(
    backend: Backend,
) -> None:
    events: list[str] = []

    def record(name: str) -> None:
        events.append(name)

    def lock_book(
        session: AsyncSession, command: LoreTypes.GetOwnedLorebooksCommand
    ) -> list[LoreTypes.LorebookInfo]:
        record("book")
        return [backend.book]

    def update_character(session: AsyncSession, command: object) -> SimpleNamespace:
        record("write")
        return SimpleNamespace(id=backend.character_id)

    backend.operations["get_owned_characters"].side_effect = lambda *_: record(
        "characters"
    )
    backend.operations["get_owned_lorebooks"].side_effect = lock_book
    backend.operations["acquire_tag_names"].side_effect = lambda *_: record("names")
    backend.operations["update_character"].side_effect = update_character
    async with AsyncSession() as session:
        await Publication.publish_studio(session, backend.command)
    assert events == ["characters", "book", "names", "write"]
    acquired = backend.operations["acquire_tag_names"].await_args
    assert acquired is not None and acquired.args[1].names == (
        "work-tag",
        "first",
        "second",
    )
    locked = backend.operations["get_owned_characters"].await_args
    assert locked is not None and locked.args[1].ids == (backend.character_id,)
    assert locked.args[1].owner_id == backend.command.owner_id and locked.args[1].lock


@pytest.mark.asyncio
async def test_name_acquisition_failure_rolls_back_before_component_writes(
    backend: Backend,
) -> None:
    backend.operations["acquire_tag_names"].side_effect = ValueError(
        "name acquisition failed"
    )
    async with AsyncSession() as session:
        events = track_transactions(session)
        with pytest.raises(ValueError, match="name acquisition failed"):
            await Publication.publish_studio(session, backend.command)
    assert events == ["rollback"]
    for name in (
        "update_character",
        "update_lorebook",
        "publish_product",
        "mark_studio_publication",
    ):
        backend.operations[name].assert_not_awaited()


@pytest.mark.asyncio
async def test_http_reused_snapshot_receipt_replays_after_next_revision(
    backend: Backend,
) -> None:
    prior = deepcopy(backend.draft.publication_release)
    assert prior is not None
    prior.update(
        {**asdict(backend.release), "snapshot_id": str(backend.release.snapshot_id)}
    )
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft,
        publication_digest=backend.draft.content_digest,
        publication_release=prior,
    )
    async with AsyncSession() as session:
        app = http_app(session, backend.command.owner_id)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://studio.test"
        ) as client:
            url = f"/products/{backend.command.product_id}/studio-publication"
            body = request(backend.command.expected_revision, backend.command.model_id)
            accepted = await client.post(url, json=body)
            assert accepted.status_code == 200
            marked = backend.operations["mark_studio_publication"].await_args
            assert marked is not None
            backend.operations[
                "get_studio_draft_for_publication"
            ].return_value = replace(
                backend.draft,
                revision=3,
                content_digest="later-draft",
                publication_release={**prior, "_studio": marked.args[1].mapping},
            )
            backend.operations["mark_studio_publication"].reset_mock()
            replay = await client.post(url, json=body)
            assert replay.status_code == 200 and replay.json() == accepted.json()
            conflict = await client.post(url, json={**body, "body": "Different"})
            assert conflict.status_code == 409
    backend.operations["mark_studio_publication"].assert_not_awaited()
    backend.operations["publish_product"].assert_not_awaited()
    backend.operations["acquire_tag_names"].assert_not_awaited()
