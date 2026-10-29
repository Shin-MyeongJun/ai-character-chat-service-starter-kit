"""Snapshot-only composition, notice scopes and media session/reader ownership."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.snapshot.product import (
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
)
from app.modules.asset_storage import types as AssetTypes
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types
from app.modules.content.product.repository.publication import SnapshotCompositionRow
from app.modules.content.product.service import views
from app.modules.content.product.service.views import notices
from app.modules.content.product.service.views.media import ProductMediaService
from app.modules.llm import types as LlmTypes


def product(latest_snapshot_id):
    now = datetime.now(UTC)
    return types.ProductStateInfo(
        id=uuid4(),
        title="Draft",
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
        latest_snapshot_id=latest_snapshot_id,
    )


def snapshot(product_id, snapshot_id=None, version=1):
    return types.ProductSnapshotInfo(
        snapshot_id or uuid4(),
        product_id,
        version,
        {"title": "Published", "description": None},
        datetime.now(UTC) - timedelta(days=1),
        "Expired for execution",
    )


@pytest.mark.asyncio
async def test_runtime_composes_only_snapshot_ids_even_after_source_deletion(
    monkeypatch,
):
    snapshot_id = uuid4()
    character = CharacterTypes.CharacterSnapshotInfo(
        uuid4(),
        None,
        1,
        {"name": "Saved", "persona_prompt": "Saved persona", "description": None},
    )
    book = LorebookTypes.LorebookSnapshotInfo(uuid4(), None, 2, {"entries": []})
    slots = SnapshotCompositionRow(
        [
            ProductSnapshotCharacter(
                id=uuid4(),
                character_snapshot_id=character.id,
                role_order=0,
                role_name=None,
                is_primary=True,
            )
        ],
        [
            ProductSnapshotLorebook(
                id=uuid4(),
                lorebook_snapshot_id=book.id,
                role="main",
                priority=1,
                is_required=True,
                scope="all",
            )
        ],
        [],
        [],
    )
    monkeypatch.setattr(
        views.Repository, "get_snapshot_composition", AsyncMock(return_value=slots)
    )
    characters = AsyncMock(return_value=[character])
    books = AsyncMock(return_value=[book])
    monkeypatch.setattr(
        views.CharacterQueryService, "get_character_snapshots", characters
    )
    monkeypatch.setattr(views.LorebookQueryService, "get_lorebook_snapshots", books)
    session = object()
    result = await views.get_snapshot_runtime(
        session, types.ProductSnapshotCommand(snapshot_id)
    )
    assert result.characters == {character.id: character}
    assert result.lorebooks == {book.id: book}
    assert result.composition.characters[0].id == slots.characters[0].id
    assert character.id != slots.characters[0].id
    characters.assert_awaited_once_with(
        session, CharacterTypes.GetCharacterSnapshotsCommand((character.id,))
    )
    books.assert_awaited_once_with(
        session, LorebookTypes.GetLorebookSnapshotsCommand((book.id,))
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("published", [True, False])
async def test_public_notice_uses_access_scope_and_can_describe_expired_snapshot(
    monkeypatch, published
):
    state = product(uuid4() if published else None)
    saved = snapshot(state.id, state.latest_snapshot_id)
    access = AsyncMock(return_value=state)
    get_snapshot = AsyncMock(return_value=saved)
    notice = LlmTypes.ModelNoticeView(state="paused", reason="model_missing")
    model_notice = AsyncMock(return_value=notice)
    monkeypatch.setattr(notices.QueryService, "get_accessible_product", access)
    monkeypatch.setattr(notices.QueryService, "get_product_snapshot", get_snapshot)
    monkeypatch.setattr(
        notices.QueryService,
        "get_snapshot_composition",
        AsyncMock(return_value=types.SnapshotCompositionInfo([], [], [], [])),
    )
    monkeypatch.setattr(notices, "execution_notice", model_notice)
    session = object()
    command = types.PublishedProductCommand(product_id=state.id, user_id=None)
    if published:
        result = await notices.get_published_product(session, command)
        assert result.title == "Published" and result.model_notice == notice
        assert result.snapshot_id == saved.id
        model_notice.assert_awaited_once_with(
            session, LlmTypes.ExecutionNoticeCommand(snapshot=saved)
        )
    else:
        with pytest.raises(LookupError, match="Published product not found"):
            await notices.get_published_product(session, command)
        get_snapshot.assert_not_awaited()
        model_notice.assert_not_awaited()
    access.assert_awaited_once_with(
        session, types.GetAccessibleProductCommand(product_id=state.id, user_id=None)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["normal", "legacy", "missing_parent"])
async def test_pending_updates_keep_conversation_scope_and_no_note_filter(
    monkeypatch, case
):
    state = product(uuid4())
    current = snapshot(state.id)
    conversation = ConversationTypes.ConversationInfo(
        uuid4(),
        uuid4(),
        state.id,
        None if case == "legacy" else current.id,
        current.id,
        None,
        datetime.now(UTC),
    )
    owned = AsyncMock(return_value=conversation)
    monkeypatch.setattr(notices, "get_owned_conversation", owned)
    monkeypatch.setattr(
        notices.QueryService, "get_product_snapshot", AsyncMock(return_value=current)
    )
    get_state = AsyncMock(return_value=None if case == "missing_parent" else state)
    monkeypatch.setattr(notices.QueryService, "get_product_state", get_state)
    next_snapshot = snapshot(state.id, version=2)
    updates = AsyncMock(
        return_value=[
            (next_snapshot, types.ReleaseNoteInfo("New", "Details", "media", "choice")),
            (snapshot(state.id, version=3), None),
        ]
    )
    monkeypatch.setattr(notices.QueryService, "list_product_releases", updates)
    monkeypatch.setattr(notices, "execution_notice", AsyncMock(return_value=None))
    session = object()
    command = types.PendingUpdatesCommand(
        conversation_id=conversation.id, user_id=conversation.user_id
    )
    if case == "legacy":
        with pytest.raises(ValueError, match="Legacy conversation"):
            await notices.get_pending_updates(session, command)
        get_state.assert_not_awaited()
    elif case == "missing_parent":
        with pytest.raises(AssertionError, match="Conversation product disappeared"):
            await notices.get_pending_updates(session, command)
        updates.assert_not_awaited()
    else:
        result = await notices.get_pending_updates(session, command)
        assert [item.snapshot_id for item in result.updates] == [next_snapshot.id]
        assert result.current_expires_at == current.expires_at
        assert result.latest_snapshot_id == state.latest_snapshot_id
        updates.assert_awaited_once_with(
            session,
            types.ListProductReleasesCommand(
                product_id=state.id, after_version=current.version
            ),
        )
    owned.assert_awaited_once_with(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=conversation.id, user_id=conversation.user_id
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("same_product", [True, False])
async def test_version_notice_requires_owner_and_snapshot_membership(
    monkeypatch, same_product
):
    state = product(uuid4())
    saved = snapshot(state.id if same_product else uuid4())
    owner = AsyncMock()
    model_notice = AsyncMock(return_value=None)
    monkeypatch.setattr(notices.QueryService, "get_owned_product", owner)
    monkeypatch.setattr(
        notices.QueryService, "get_product_snapshot", AsyncMock(return_value=saved)
    )
    monkeypatch.setattr(notices, "execution_notice", model_notice)
    session = object()
    command = types.VersionAvailabilityCommand(
        product_id=state.id, snapshot_id=saved.id, owner_id=state.owner_id
    )
    if same_product:
        result = await notices.get_version_availability(session, command)
        assert (
            result.expires_at == saved.expires_at
            and result.expiry_reason == saved.expiry_reason
        )
    else:
        with pytest.raises(LookupError, match="Version not found"):
            await notices.get_version_availability(session, command)
        model_notice.assert_not_awaited()
    owner.assert_awaited_once_with(
        session, types.OwnedProductCommand(product_id=state.id, owner_id=state.owner_id)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "access", "expired", "foreign"])
async def test_media_reads_only_authorized_snapshot_ids_after_session_exit(
    monkeypatch, failure
):
    product_id, snapshot_id, media_id, user_id, character_snapshot_id = [
        uuid4() for _ in range(5)
    ]
    context = {"open": False}
    sessions = []

    @asynccontextmanager
    async def session_factory():
        async with AsyncSession() as session:
            sessions.append(session)
            context["open"] = True
            try:
                yield session
            finally:
                context["open"] = False

    access = AsyncMock(
        side_effect=LookupError("Denied") if failure == "access" else None
    )
    available = AsyncMock(
        return_value=types.ProductSnapshotInfo(
            snapshot_id,
            uuid4() if failure == "foreign" else product_id,
            1,
            {"title": "Published"},
            None,
            None,
        ),
        side_effect=ValueError("Version expired") if failure == "expired" else None,
    )
    composition = AsyncMock(
        return_value=types.SnapshotCompositionInfo(
            [
                types.SnapshotCharacterInfo(
                    uuid4(), character_snapshot_id, 0, None, True
                )
            ],
            [],
            [],
            [],
        )
    )
    from app.modules.content.product.service.views import media as MediaViews

    monkeypatch.setattr(MediaViews.QueryService, "get_accessible_product", access)
    monkeypatch.setattr(MediaViews.QueryService, "ensure_snapshot_available", available)
    monkeypatch.setattr(
        MediaViews.QueryService, "get_snapshot_composition", composition
    )
    reader = AsyncMock(spec=AssetTypes.AsyncAssetReader)
    reader.read.return_value = b"image"
    opened = AssetTypes.AssetReadInfo(
        AssetTypes.AssetMetadataInfo(
            "test_local", "test", "character-media/object", 5, "image/png"
        ),
        reader,
    )
    client = AsyncMock(spec=CharacterMediaService)

    async def read(command):
        assert not context["open"] and not sessions[0].in_transaction()
        return opened

    client.read_snapshot_media.side_effect = read
    service = ProductMediaService(session_factory, client)
    command = types.ReadProductMediaCommand(product_id, snapshot_id, media_id, user_id)
    if failure:
        with pytest.raises(ValueError if failure == "expired" else LookupError):
            await service.read_product_media(command)
        client.read_snapshot_media.assert_not_awaited()
        composition.assert_not_awaited()
    else:
        result = await service.read_product_media(command)
        assert result is opened and await result.read() == b"image"
        client.read_snapshot_media.assert_awaited_once_with(
            CharacterTypes.ReadSnapshotMediaCommand(
                media_id=media_id, snapshot_ids=(character_snapshot_id,)
            )
        )
        reader.aclose.assert_not_awaited()
        await result.aclose()
        reader.aclose.assert_awaited_once()
    assert not context["open"]
    access.assert_awaited_once_with(
        sessions[0],
        types.GetAccessibleProductCommand(product_id=product_id, user_id=user_id),
    )
