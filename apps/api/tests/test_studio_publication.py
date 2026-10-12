"""Studio publication validation and retry behavior without a database."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.content.product import types as ProductTypes
from app.use_cases import studio_publication as publication


def document():
    return {
        "version": 2,
        "work": {"title": "Story", "introduction": "Intro", "visibility": "비공개", "defaultSceneId": "scene", "worldRules": "Rules"},
        "characters": [{"id": "hero", "name": "Hero", "persona": "Waits for the reader.", "assets": []}],
        "lorebooks": [{"id": "world", "title": "World", "content": "A quiet place.", "category": "세계관", "activation": "always", "enabled": True}],
        "scenes": [{"id": "scene", "title": "Arrival", "characterId": "hero", "background": "A hall.", "opening": "Welcome.", "initialNotes": ""}],
    }


def command():
    return publication.PublishStudioCommand(uuid4(), uuid4(), 2, uuid4(), "low", "First release", "Ready to read")


def test_publication_rejects_missing_character_and_unuploaded_assets():
    value = document()
    value["scenes"][0]["characterId"] = "missing"
    with pytest.raises(ValueError, match="character"):
        publication._publication_content(value)
    value = document()
    value["characters"][0]["assets"] = [{"id": "local-image"}]
    with pytest.raises(ValueError, match="Upload"):
        publication._publication_content(value)


@pytest.mark.parametrize("section,field,invalid", [
    ("work", "visibility", []),
    ("characters", "dialogue", 123),
    ("characters", "assets", {}),
    ("scenes", "background", 123),
    ("lorebooks", "keywords", "invalid"),
])
def test_publication_rejects_malformed_optional_fields(section, field, invalid):
    value = document()
    row = value[section] if section == "work" else value[section][0]
    row[field] = invalid
    with pytest.raises(ValueError, match="Invalid"):
        publication._publication_content(value)


@pytest.mark.asyncio
async def test_same_revision_publication_retry_returns_saved_release(monkeypatch):
    @asynccontextmanager
    async def transaction(_session):
        yield

    release = ProductTypes.ReleaseInfo(uuid4(), 1, "First release", "Ready to read", "initial", "choice")
    draft = SimpleNamespace(
        revision=2, document=document(), content_digest="same", publication_digest="same",
        publication_release={"snapshot_id": str(release.snapshot_id), "version": 1,
                             "summary": release.summary, "body": release.body,
                             "change_kind": release.change_kind, "update_policy": release.update_policy},
    )
    create = AsyncMock(side_effect=AssertionError("Retry must not create source rows"))
    monkeypatch.setattr(publication, "use_case_transaction", transaction)
    monkeypatch.setattr(publication, "get_studio_draft_for_publication", AsyncMock(return_value=draft))
    monkeypatch.setattr(publication.ProductQuery, "get_owned_product", AsyncMock(return_value=SimpleNamespace(
        title="Story", description="Intro", opening_message="Welcome.", visibility="private",
    )))
    monkeypatch.setattr(publication.CharacterCommand, "create_character", create)
    assert await publication.publish_studio(object(), command()) == release
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_initial_publication_uses_one_composed_transaction(monkeypatch):
    active = False

    @asynccontextmanager
    async def transaction(_session):
        nonlocal active
        active = True
        try:
            yield
        finally:
            active = False

    draft = SimpleNamespace(revision=2, document=document(), content_digest="digest", publication_digest=None, publication_release=None)
    draft.document["work"]["tags"] = ["work-tag"]
    draft.document["characters"][0]["tags"] = ["character-tag"]
    draft.document["lorebooks"][0]["tags"] = ["lore-tag"]
    from app.modules.content.product.service import tags as ProductTagsService
    product_tags = AsyncMock(return_value=())
    monkeypatch.setattr(ProductTagsService, "replace_public_tags", product_tags)
    character_id, book_id, start_id = uuid4(), uuid4(), uuid4()
    release = ProductTypes.ReleaseInfo(uuid4(), 1, "First release", "Ready to read", "initial", "choice")
    monkeypatch.setattr(publication, "use_case_transaction", transaction)
    monkeypatch.setattr(publication, "get_studio_draft_for_publication", AsyncMock(return_value=draft))
    monkeypatch.setattr(publication.ProductQuery, "get_owned_product", AsyncMock(return_value=SimpleNamespace(
        title="Story", description="Intro", opening_message="Welcome.", visibility="private",
    )))
    monkeypatch.setattr(publication.CharacterCommand, "create_character", AsyncMock(return_value=SimpleNamespace(id=character_id)))
    monkeypatch.setattr(publication.LoreCommand, "create_lorebook", AsyncMock(return_value=SimpleNamespace(id=book_id)))
    monkeypatch.setattr(publication.LoreCommand, "create_lorebook_entry", AsyncMock(side_effect=[SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4()), SimpleNamespace(id=start_id)]))
    compose = AsyncMock()
    settings = AsyncMock()
    publish = AsyncMock(return_value=release)
    mark = AsyncMock()
    monkeypatch.setattr(publication.CompositionCommand, "replace_composition", compose)
    monkeypatch.setattr(publication.SettingsCommand, "set_settings", settings)
    monkeypatch.setattr(publication.ReleasesCommand, "publish_product", publish)
    monkeypatch.setattr(publication, "mark_studio_publication", mark)
    request = command()
    assert await publication.publish_studio(object(), request) == release
    assert active is False
    assert compose.await_args.args[1].value.characters[0].character_id == character_id
    assert settings.await_args.args[1].value.start_entry_ids == (start_id,)
    assert mark.await_args.args[1].content_digest == "digest"

    assert publication.CharacterCommand.create_character.await_args.args[1].tags == ("character-tag",)
    assert publication.LoreCommand.create_lorebook.await_args.args[1].tags == ("lore-tag",)
    assert product_tags.await_args.args[1].names == ("work-tag",)


@pytest.mark.parametrize("section", ["work", "characters", "lorebooks"])
@pytest.mark.parametrize("invalid", ["not a list", ["   "], [123]])
def test_publication_rejects_invalid_tag_names(section, invalid):
    value = document()
    row = value[section] if section == "work" else value[section][0]
    row["tags"] = invalid
    with pytest.raises(ValueError, match="tags"):
        publication._publication_content(value)
