"""Follow-up studio publication contracts with public-service doubles."""

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

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
    patch(Publication.CharacterCommand, "update_character", MagicMock(id=character_id))
    patch(Publication.CharacterCommand, "create_character")
    patch(Publication.CharacterQuery, "list_character_assets", [])
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
