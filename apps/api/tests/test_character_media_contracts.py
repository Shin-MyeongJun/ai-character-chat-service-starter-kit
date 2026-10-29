"""Offline attachment contracts and reference scopes; no real storage or PG locking."""

import json
from datetime import UTC, datetime
from typing import Literal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import CharacterAsset, CharacterImage
from app.db.models.character_media import CharacterMedia
from app.db.models.snapshot.character import (
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types
from app.modules.content.character.service import media as MediaService


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["image", "asset"])
@pytest.mark.parametrize("state", ["new", "replay", "deleted"])
async def test_managed_attachment_preserves_creation_replay_and_deleted_receipt(
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["image", "asset"],
    state: str,
) -> None:
    now = datetime.now(UTC)
    media_id, character_id, owner_id = uuid4(), uuid4(), uuid4()
    url = f"/characters/media/{media_id}/content"
    image_command = Types.CreateCharacterImageCommand(
        character_id=character_id,
        owner_id=owner_id,
        emotion_tag="happy",
        image_url=url,
        is_default=True,
    )
    asset_command = Types.CreateCharacterAssetCommand(
        character_id=character_id,
        owner_id=owner_id,
        asset_type="audio",
        purpose="voice",
        file_url=url,
    )
    if kind == "image":
        saved = CharacterImage(
            id=uuid4(),
            character_id=character_id,
            emotion_tag="happy",
            image_url=url,
            is_default=True,
            created_at=now,
            updated_at=now,
        )
        binding = json.dumps(["image", "happy", True])
    else:
        saved = CharacterAsset(
            id=uuid4(),
            character_id=character_id,
            asset_type="audio",
            purpose="voice",
            file_url=url,
            created_at=now,
            updated_at=now,
        )
        binding = json.dumps(["asset", "audio", "voice"])
    media = CharacterMedia(
        id=media_id,
        character_id=character_id,
        owner_id=owner_id,
        request_id=uuid4(),
        storage_kind="test_local",
        storage_id="local",
        object_key="media/object",
        content_type="image/png" if kind == "image" else "audio/mpeg",
        size_bytes=8,
        original_filename="original",
        purpose="test",
        sha256="a" * 64,
        state="ready",
        binding=None if state == "new" else binding,
        updated_at=now,
    )
    monkeypatch.setattr(MediaService, "_get_owned_character", AsyncMock())
    get_media = AsyncMock(return_value=media)
    get_attachment = AsyncMock(return_value=saved if state == "replay" else None)
    create = AsyncMock(return_value=saved)
    bind = AsyncMock()
    monkeypatch.setattr(Repository, "get_media", get_media)
    monkeypatch.setattr(Repository, "get_media_attachment", get_attachment)
    monkeypatch.setattr(Repository, "create_media_attachment", create)
    monkeypatch.setattr(Repository, "bind_media", bind)
    session = AsyncMock(spec=AsyncSession)

    async def attach() -> Types.CharacterImageInfo | Types.CharacterAssetInfo:
        if kind == "image":
            return await MediaService._attach_character_media(
                session, image_command, "image"
            )
        return await MediaService._attach_character_media(
            session, asset_command, "asset"
        )

    if state == "deleted":
        with pytest.raises(ValueError, match="Attachment was deleted"):
            await attach()
        create.assert_not_awaited()
        bind.assert_not_awaited()
    else:
        result = await attach()
        assert result.id == saved.id and result.character_id == character_id
        if kind == "image":
            assert isinstance(result, Types.CharacterImageInfo)
            assert result.image_url == url and result.is_default
            assert result.emotion_tag == "happy"
        else:
            assert isinstance(result, Types.CharacterAssetInfo)
            assert result.file_url == url and result.asset_type == "audio"
            assert result.purpose == "voice"
        if state == "new":
            bind.assert_awaited_once_with(session, media_id, binding)
            create.assert_awaited_once_with(
                session,
                image_command if kind == "image" else asset_command,
                media_id,
                kind,
            )
        else:
            create.assert_not_awaited()
            bind.assert_not_awaited()
    get_media.assert_awaited_once_with(session, media_id, lock=True)


@pytest.mark.asyncio
async def test_reference_scope_distinguishes_cleanup_from_authorized_snapshots() -> (
    None
):
    metadata = MetaData()
    tables = {}
    for model in (
        CharacterImage,
        CharacterAsset,
        CharacterSnapshotImage,
        CharacterSnapshotAsset,
    ):
        columns = [Column("id", Uuid, primary_key=True), Column("media_id", Uuid)]
        if model in (CharacterSnapshotImage, CharacterSnapshotAsset):
            columns.append(Column("character_snapshot_id", Uuid))
        tables[model] = Table(model.__tablename__, metadata, *columns)
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            draft_media_id, snapshot_media_id, snapshot_id = uuid4(), uuid4(), uuid4()
            connection.execute(
                tables[CharacterImage]
                .insert()
                .values(id=uuid4(), media_id=draft_media_id)
            )
            connection.execute(
                tables[CharacterSnapshotAsset]
                .insert()
                .values(
                    id=uuid4(),
                    media_id=snapshot_media_id,
                    character_snapshot_id=snapshot_id,
                )
            )
            session = AsyncMock(spec=AsyncSession)
            session.scalar.side_effect = connection.scalar
            assert await Repository.has_media_references(session, draft_media_id)
            assert await Repository.has_media_references(session, snapshot_media_id)
            assert not await Repository.has_media_references(
                session, draft_media_id, (snapshot_id,)
            )
            assert not await Repository.has_media_references(
                session, snapshot_media_id, ()
            )
            assert not await Repository.has_media_references(
                session, snapshot_media_id, (uuid4(),)
            )
            assert await Repository.has_media_references(
                session, snapshot_media_id, (snapshot_id,)
            )
            assert not await Repository.has_media_references(session, uuid4())
    finally:
        engine.dispose()
