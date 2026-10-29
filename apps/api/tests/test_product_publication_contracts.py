"""Offline publication payload/slot contracts and release policies; no PG locking."""

import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_composition_contracts import start_entry
from test_product_core_contracts import database as core_database_fixture

from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
)
from app.db.models.product_release import ProductReleaseNote, ProductReleaseNoteRevision
from app.db.models.snapshot.product import (
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
    ProductSnapshotLorebookCharacter,
    ProductSnapshotPolicyChange,
    ProductSnapshotStartSet,
)
from app.modules.content.character import types as CharacterTypes
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types
from app.modules.content.product.repository import publication as PublicationRepository
from app.modules.content.product.repository import releases as ReleasesRepository
from app.modules.content.product.repository.composition import ProductCompositionRow
from app.modules.content.product.service.command import publication, releases

core_database = core_database_fixture


@pytest.fixture
def publication_database(core_database):
    sync_session, session = core_database
    metadata = MetaData()
    for model in (
        ProductSnapshotCharacter,
        ProductSnapshotLorebook,
        ProductSnapshotLorebookCharacter,
        ProductSnapshotStartSet,
        ProductSnapshotPolicyChange,
        ProductReleaseNote,
        ProductReleaseNoteRevision,
    ):
        columns = []
        for column in model.__table__.columns:
            default = None
            if column.name == "id":
                default = text("(lower(hex(randomblob(16))))")
            elif column.name in ("created_at", "corrected_at"):
                default = text("CURRENT_TIMESTAMP")
            columns.append(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                    server_default=default,
                )
            )
        Table(model.__tablename__, metadata, *columns)
    metadata.create_all(sync_session.get_bind())
    session.get.side_effect = sync_session.get
    yield sync_session, session


@pytest.mark.asyncio
async def test_builder_keeps_digest_payload_and_snapshot_slot_identities(
    publication_database, monkeypatch
):
    sync_session, session = publication_database
    owner_id, product_id, model_id, provider_id = uuid4(), uuid4(), uuid4(), uuid4()
    product = Product(
        id=product_id,
        owner_id=owner_id,
        title="Published work",
        description=None,
        opening_message="Opening",
        visibility="private",
        status="draft",
        default_model_id=model_id,
        reasoning_effort="medium",
        replacement_policy={},
    )
    sync_session.add(product)
    sync_session.flush()
    character = ProductCharacter(
        id=uuid4(),
        character_id=uuid4(),
        role_order=0,
        role_name="Lead",
        is_primary=True,
    )
    book = ProductLorebook(
        id=uuid4(),
        lorebook_id=uuid4(),
        role="main",
        priority=4,
        is_required=True,
        scope="selected",
    )
    row = ProductCompositionRow(
        [character],
        [book],
        [
            ProductLorebookCharacter(
                product_character_id=character.id, product_lorebook_id=book.id
            )
        ],
    )
    entry = start_entry(uuid4(), book.lorebook_id)
    entry.metadata["studio_scene_v1"] = {"opening": "Hello", "language": "한국어"}
    start = types.ProductStartSetInfo(
        uuid4(), product_id, book.lorebook_id, entry.id, 0
    )
    character_snapshot = CharacterTypes.CharacterSnapshotInfo(
        uuid4(),
        character.character_id,
        1,
        {"name": "Hero", "description": None, "persona_prompt": "Persona"},
    )
    lorebook_snapshot = LorebookTypes.LorebookSnapshotInfo(
        uuid4(),
        book.lorebook_id,
        1,
        {"title": "Lore", "description": None, "entries": []},
    )
    monkeypatch.setattr(
        publication.Repository, "get_product_composition", AsyncMock(return_value=row)
    )
    monkeypatch.setattr(
        publication.CharacterQueryService, "get_owned_characters", AsyncMock()
    )
    monkeypatch.setattr(
        publication.LorebookQueryService, "get_owned_lorebooks", AsyncMock()
    )
    monkeypatch.setattr(
        publication.SettingsCommandService,
        "_validate_publication",
        AsyncMock(return_value=((), [start])),
    )
    monkeypatch.setattr(
        publication.SettingsCommandService,
        "_validate_model",
        AsyncMock(
            return_value=SimpleNamespace(
                id=model_id,
                provider_id=provider_id,
                model_name="test-model",
                capabilities={"model_family": "test"},
            )
        ),
    )
    monkeypatch.setattr(
        publication.LlmQueryService,
        "get_provider",
        AsyncMock(return_value=SimpleNamespace(name="test-provider")),
    )
    monkeypatch.setattr(
        publication.CharacterCommandService,
        "freeze_character",
        AsyncMock(return_value=character_snapshot),
    )
    monkeypatch.setattr(
        publication.LorebookCommandService,
        "freeze_lorebook",
        AsyncMock(return_value=lorebook_snapshot),
    )
    monkeypatch.setattr(
        publication.LorebookQueryService,
        "get_lorebook_entry",
        AsyncMock(return_value=entry),
    )
    session.in_transaction.return_value = True
    result = await publication._build_publication(
        session, types.BuildPublicationCommand(product_id=product_id, owner_id=owner_id)
    )
    profile = {
        "title": "Published work",
        "description": None,
        "opening_message": "Opening",
        "model": {
            "id": str(model_id),
            "provider_id": str(provider_id),
            "provider": "test-provider",
            "name": "test-model",
            "family": "test",
            "reasoning_effort": "medium",
        },
        "replacement_policy": {},
    }
    canonical = {
        "product": profile,
        "characters": [
            {
                "source_id": str(character.character_id),
                "data": character_snapshot.snapshot_data,
                "order": 0,
                "role": "Lead",
                "primary": True,
            }
        ],
        "lorebooks": [
            {
                "source_id": str(book.lorebook_id),
                "data": lorebook_snapshot.snapshot_data,
                "role": "main",
                "priority": 4,
                "required": True,
                "scope": "selected",
                "targets": [str(character.character_id)],
            }
        ],
        "starts": [str(entry.id)],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    assert result.snapshot_data == {
        **profile,
        "content_digest": digest,
        "studio_start_options": {str(entry.id): entry.metadata["studio_scene_v1"]},
    }
    assert product.latest_snapshot_id == result.id and result.version == 1
    slots = await PublicationRepository.get_snapshot_composition(session, result.id)
    assert slots.characters[0].id != character.id
    assert slots.characters[0].character_snapshot_id == character_snapshot.id
    assert slots.books[0].id != book.id
    assert slots.books[0].lorebook_snapshot_id == lorebook_snapshot.id
    assert slots.targets[0].product_character_id == slots.characters[0].id
    assert slots.targets[0].product_lorebook_id == slots.books[0].id
    assert slots.starts[0].source_entry_id == entry.id and slots.starts[0].title is None
    assert await PublicationRepository.list_snapshot_character_ids(
        session, result.id
    ) == (character_snapshot.id,)


@pytest.mark.asyncio
async def test_release_rows_keep_missing_notes_and_corrections_keep_history(
    publication_database,
):
    sync_session, session = publication_database
    product_id, owner_id = uuid4(), uuid4()
    first = await PublicationRepository.create_product_snapshot(
        session, product_id, {"title": "First"}
    )
    second = await PublicationRepository.create_product_snapshot(
        session, product_id, {"title": "Second"}
    )
    await ReleasesRepository.create_release_note(
        session, second.id, "Before", "Old body", "media", "choice"
    )
    rows = await ReleasesRepository.list_product_release_rows(session, product_id, 0, 2)
    assert [snapshot.version for snapshot, _ in rows] == [1, 2]
    assert rows[0][1] is None and rows[1][1].summary == "Before"
    assert (
        await ReleasesRepository.get_release_note(session, first.id, lock=True) is None
    )
    corrected = await ReleasesRepository.correct_release_note(
        session, second.id, owner_id, "After", "New body", datetime.now(UTC)
    )
    assert corrected.summary == "After" and corrected.change_kind == "media"
    assert corrected.update_policy == "choice"
    history = sync_session.scalars(select(ProductReleaseNoteRevision)).one()
    assert history.editor_id == owner_id
    assert (history.previous_summary, history.previous_body) == ("Before", "Old body")
    assert [
        row[0].id
        for row in await ReleasesRepository.list_product_release_rows(
            session, product_id, 1, 2
        )
    ] == [second.id]
    assert (
        await ReleasesRepository.list_product_release_rows(session, product_id, 2) == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prior", "changed", "removed", "auto_apply", "kind", "policy"),
    [
        (False, False, False, True, "initial", "choice"),
        (True, False, False, True, "media", "automatic"),
        (True, False, False, False, "media", "choice"),
        (True, True, False, True, "content", "choice"),
        (True, False, True, True, "content", "choice"),
    ],
)
async def test_publish_keeps_content_and_media_policy(
    monkeypatch, prior, changed, removed, auto_apply, kind, policy
):
    product_id, owner_id = uuid4(), uuid4()
    previous = types.ProductSnapshotInfo(
        uuid4(), product_id, 1, {"title": "Old", "content_digest": "same"}, None, None
    )
    snapshot = types.ProductSnapshotInfo(
        uuid4(),
        product_id,
        2,
        {"title": "New", "content_digest": "changed" if changed else "same"},
        None,
        None,
    )
    monkeypatch.setattr(
        releases.QueryService,
        "get_owned_product",
        AsyncMock(
            return_value=SimpleNamespace(
                latest_snapshot_id=previous.id if prior else None
            )
        ),
    )
    monkeypatch.setattr(
        releases.QueryService, "get_product_snapshot", AsyncMock(return_value=previous)
    )
    monkeypatch.setattr(
        releases, "_build_publication", AsyncMock(return_value=snapshot)
    )
    manifest = frozenset({("image", "source", "happy", "image.png")})
    media = AsyncMock(side_effect=[manifest, frozenset() if removed else manifest])
    monkeypatch.setattr(releases, "_get_media_manifest", media)
    write = AsyncMock()
    monkeypatch.setattr(releases.Repository, "create_release_note", write)
    async with AsyncSession() as session:
        result = await releases.publish_product(
            session,
            types.PublishCommand(
                product_id=product_id,
                owner_id=owner_id,
                value=types.ReleaseNoteCommand("Summary", "Body", auto_apply),
            ),
        )
        assert (result.change_kind, result.update_policy) == (kind, policy)
        write.assert_awaited_once_with(
            session, snapshot.id, "Summary", "Body", kind, policy
        )
        assert not session.in_transaction()
    assert media.await_count == (2 if prior else 0)
