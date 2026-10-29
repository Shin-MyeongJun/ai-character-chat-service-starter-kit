# 원본·이미지·에셋·발행 복사본·업로드 예약의 저장소. 상위 서비스가 소유권과 트랜잭션을 조율한다.
# 일반 페이지는 created_at/id 내림차순, 이미지는 기본 이미지 우선 후 최신순이다.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, overload
from uuid import UUID, uuid4

from sqlalchemy import Select, exists, func, select, update

# This module owns these connections; dictionary data is read through tag service.
from sqlalchemy import delete as tag_delete
from sqlalchemy import select as tag_select
from sqlalchemy.dialects.postgresql import insert as tag_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.models import character as character_models
from app.db.models.character import (
    Character,
    CharacterAsset,
    CharacterImage,
    CharacterVisibility,
)
from app.db.models.character_media import CharacterMedia
from app.db.models.snapshot.character import (
    CharacterSnapshot,
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
from app.db.models.tag import CharacterInternalTag, CharacterTag
from app.db.pagination import fetch_cursor_page
from app.modules.content.character import types as Types
from app.modules.content.character.types import CharacterCursor

DEFAULT_CHARACTER_LIST_LIMIT = 50
MAX_CHARACTER_LIST_LIMIT = 100


@dataclass(frozen=True)
class CharacterPageRow:
    items: list[Character]
    next_cursor: Types.CharacterCursor | None


async def _fetch_character_page(
    session: AsyncSession,
    stmt: Select[tuple[Character]],
    *,
    cursor: CharacterCursor | None,
    limit: int,
) -> CharacterPageRow:
    return await fetch_cursor_page(
        session,
        stmt,
        created_at=Character.created_at,
        id_column=Character.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_CHARACTER_LIST_LIMIT,
        cursor_factory=CharacterCursor,
        page_factory=CharacterPageRow,
    )


# Character


async def create_character(
    session: AsyncSession,
    character: Character,
) -> Character:
    session.add(character)
    await session.flush()
    await session.refresh(character)
    return character


async def get_character_by_id(
    session: AsyncSession,
    character_id: UUID,
) -> Character | None:
    stmt = select(Character).where(Character.id == character_id)

    result = await session.scalars(stmt)
    return result.one_or_none()


async def get_character_by_id_and_owner_id(
    session: AsyncSession,
    character_id: UUID,
    owner_id: UUID,
    *,
    for_update: bool = False,
) -> Character | None:
    stmt = select(Character).where(
        Character.id == character_id,
        Character.owner_id == owner_id,
    )
    if for_update:
        stmt = stmt.with_for_update()

    result = await session.scalars(stmt)
    return result.one_or_none()


async def list_characters(
    session: AsyncSession,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    # Unrestricted collection; public visibility/moderation policies belong to callers.
    return await _fetch_character_page(
        session, select(Character), cursor=cursor, limit=limit
    )


async def list_characters_by_owner_id(
    session: AsyncSession,
    owner_id: UUID,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    stmt = select(Character).where(Character.owner_id == owner_id)

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def update_character(
    session: AsyncSession,
    character: Character,
) -> Character:
    session.add(character)
    await session.flush()
    await session.refresh(character)
    return character


async def delete_character(
    session: AsyncSession,
    character: Character,
) -> None:
    await session.delete(character)
    await session.flush()


# visibility=public만 필터한다. approved 조건·owner 조건은 없으므로 공개 노출 정책으로 단독 사용하지 않는다.
async def list_public_characters(
    session: AsyncSession,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    stmt = select(Character).where(
        Character.visibility == CharacterVisibility.PUBLIC.value
    )

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def list_characters_by_status(
    session: AsyncSession,
    status: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    stmt = select(Character).where(Character.status == status)

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def list_characters_by_visibility(
    session: AsyncSession,
    visibility: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    stmt = select(Character).where(Character.visibility == visibility)

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def search_characters_by_name(
    session: AsyncSession,
    keyword: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPageRow:
    keyword = keyword.strip()
    if not keyword:
        return CharacterPageRow(items=[], next_cursor=None)

    stmt = select(Character).where(Character.name.ilike(f"%{keyword}%"))

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


# CharacterImage


async def add_character_image(
    session: AsyncSession,
    image: CharacterImage,
) -> CharacterImage:
    session.add(image)
    await session.flush()
    await session.refresh(image)
    return image


async def list_character_images(
    session: AsyncSession,
    character_id: UUID,
) -> list[CharacterImage]:
    stmt = (
        select(CharacterImage)
        .where(CharacterImage.character_id == character_id)
        .order_by(
            CharacterImage.is_default.desc(),
            CharacterImage.created_at.desc(),
            CharacterImage.id.desc(),
        )
    )

    result = await session.scalars(stmt)
    return list(result.all())


async def get_character_image_by_id_and_character_id(
    session: AsyncSession,
    image_id: UUID,
    character_id: UUID,
) -> CharacterImage | None:
    stmt = select(CharacterImage).where(
        CharacterImage.id == image_id,
        CharacterImage.character_id == character_id,
    )

    result = await session.scalars(stmt)
    return result.one_or_none()


async def get_character_image_by_emotion_tag(
    session: AsyncSession,
    character_id: UUID,
    emotion_tag: str,
) -> CharacterImage | None:
    # (character_id, emotion_tag) is unique. Match the stored tag exactly.
    stmt = select(CharacterImage).where(
        CharacterImage.character_id == character_id,
        CharacterImage.emotion_tag == emotion_tag,
    )
    result = await session.scalars(stmt)
    return result.one_or_none()


async def get_default_character_image(
    session: AsyncSession,
    character_id: UUID,
) -> CharacterImage | None:
    stmt = select(CharacterImage).where(
        CharacterImage.character_id == character_id,
        CharacterImage.is_default.is_(True),
    )

    result = await session.scalars(stmt)
    return result.one_or_none()


async def set_default_character_image(
    session: AsyncSession,
    image_id: UUID,
    character_id: UUID,
) -> CharacterImage | None:
    stmt = select(CharacterImage).where(
        CharacterImage.id == image_id,
        CharacterImage.character_id == character_id,
    )
    result = await session.scalars(stmt)
    image = result.one_or_none()
    if image is None:
        return None

    await session.execute(
        update(CharacterImage)
        .where(CharacterImage.character_id == character_id)
        .values(is_default=False)
    )

    image.is_default = True
    await session.flush()
    await session.refresh(image)
    return image


async def delete_character_image(
    session: AsyncSession,
    image: CharacterImage,
) -> None:
    await session.delete(image)
    await session.flush()


# CharacterAsset


async def add_character_asset(
    session: AsyncSession,
    asset: CharacterAsset,
) -> CharacterAsset:
    session.add(asset)
    await session.flush()
    await session.refresh(asset)
    return asset


async def list_character_assets(
    session: AsyncSession,
    character_id: UUID,
) -> list[CharacterAsset]:
    stmt = (
        select(CharacterAsset)
        .where(CharacterAsset.character_id == character_id)
        .order_by(CharacterAsset.created_at.desc(), CharacterAsset.id.desc())
    )

    result = await session.scalars(stmt)
    return list(result.all())


async def list_character_assets_by_type(
    session: AsyncSession,
    character_id: UUID,
    asset_type: str,
) -> list[CharacterAsset]:
    stmt = (
        select(CharacterAsset)
        .where(
            CharacterAsset.character_id == character_id,
            CharacterAsset.asset_type == asset_type,
        )
        .order_by(CharacterAsset.created_at.desc(), CharacterAsset.id.desc())
    )

    result = await session.scalars(stmt)
    return list(result.all())


async def get_character_asset_by_id_and_character_id(
    session: AsyncSession,
    asset_id: UUID,
    character_id: UUID,
) -> CharacterAsset | None:
    stmt = select(CharacterAsset).where(
        CharacterAsset.id == asset_id,
        CharacterAsset.character_id == character_id,
    )

    result = await session.scalars(stmt)
    return result.one_or_none()


async def delete_character_asset(
    session: AsyncSession,
    asset: CharacterAsset,
) -> None:
    await session.delete(asset)
    await session.flush()


def _create_character_entity(
    command: Types.CreateCharacterCommand,
) -> character_models.Character:
    return character_models.Character(
        owner_id=command.owner_id,
        name=command.name,
        description=command.description,
        persona_prompt=command.persona_prompt,
        visibility=command.visibility,
        status=command.status,
        default_model_id=command.default_model_id,
    )


def _apply_character_update(
    entity: character_models.Character,
    command: Types.UpdateCharacterCommand,
) -> character_models.Character:
    entity.name = command.name
    entity.description = command.description
    entity.persona_prompt = command.persona_prompt
    entity.visibility = command.visibility
    entity.default_model_id = command.default_model_id
    return entity


def _apply_character_status_change(
    entity: character_models.Character,
    command: Types.ChangeCharacterStatusCommand,
) -> character_models.Character:
    entity.status = command.status
    return entity


def _create_character_image_entity(
    command: Types.CreateCharacterImageCommand,
) -> character_models.CharacterImage:
    return character_models.CharacterImage(
        character_id=command.character_id,
        emotion_tag=command.emotion_tag,
        image_url=command.image_url,
        is_default=command.is_default,
    )


def _create_character_asset_entity(
    command: Types.CreateCharacterAssetCommand,
) -> character_models.CharacterAsset:
    return character_models.CharacterAsset(
        character_id=command.character_id,
        asset_type=command.asset_type,
        purpose=command.purpose,
        file_url=command.file_url,
    )


async def create_character_command(
    session: AsyncSession, command: Types.CreateCharacterCommand
) -> Character:
    entity = _create_character_entity(command)
    return await create_character(session, entity)


async def update_character_command(
    session: AsyncSession, command: Types.UpdateCharacterCommand
) -> Character:
    entity = await get_character_by_id_and_owner_id(
        session, command.character_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_character_update(entity, command)
    return await update_character(session, entity)


async def change_character_status_command(
    session: AsyncSession, command: Types.ChangeCharacterStatusCommand
) -> Character:
    entity = await get_character_by_id_and_owner_id(
        session, command.character_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_character_status_change(entity, command)
    return await update_character(session, entity)


async def delete_character_command(
    session: AsyncSession, command: Types.DeleteCharacterCommand
) -> None:
    entity = await get_character_by_id_and_owner_id(
        session, command.character_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    await delete_character(session, entity)


async def delete_character_image_command(
    session: AsyncSession, command: Types.DeleteCharacterImageCommand
) -> None:
    entity = await get_character_image_by_id_and_character_id(
        session, command.image_id, command.character_id
    )
    assert entity is not None, "Previously locked record disappeared."
    await delete_character_image(session, entity)


async def delete_character_asset_command(
    session: AsyncSession, command: Types.DeleteCharacterAssetCommand
) -> None:
    entity = await get_character_asset_by_id_and_character_id(
        session, command.asset_id, command.character_id
    )
    assert entity is not None, "Previously locked record disappeared."
    await delete_character_asset(session, entity)


@dataclass(frozen=True)
class CharacterPromotionRow:
    character: Character
    images: list[CharacterImage]
    assets: list[CharacterAsset]


async def get_character_promotion(
    session: AsyncSession, character_id: UUID
) -> CharacterPromotionRow | None:
    character = await get_character_by_id(session, character_id)
    if character is None:
        return None
    images = await list_character_images(session, character_id)
    assets = await list_character_assets(session, character_id)
    return CharacterPromotionRow(character, images, assets)


async def list_owned_characters(
    session: AsyncSession,
    ids: tuple[UUID, ...],
    owner_id: UUID,
    *,
    lock: bool = False,
) -> list[Character]:
    stmt = (
        select(Character)
        .where(Character.id.in_(ids), Character.owner_id == owner_id)
        .order_by(Character.id)
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list(await session.scalars(stmt))


# MAX(version)+1 계산 자체는 잠금을 잡지 않는다. freeze를 호출하는 서비스의 원본 잠금과 함께 읽는다.
async def next_version(
    session: AsyncSession,
    cls: type[CharacterSnapshot],
    column: InstrumentedAttribute[UUID | None],
    source_id: UUID,
) -> int:
    return (
        await session.scalar(select(func.max(cls.version)).where(column == source_id))
        or 0
    ) + 1


async def freeze_character(
    session: AsyncSession, source: Types.CharacterInfo
) -> CharacterSnapshot:
    snapshot_data: Types.CharacterSnapshotV2Data = {
        "name": source.name,
        "description": source.description,
        "persona_prompt": source.persona_prompt,
    }
    snapshot = CharacterSnapshot(
        id=uuid4(),
        character_id=source.id,
        version=await next_version(
            session, CharacterSnapshot, CharacterSnapshot.character_id, source.id
        ),
        snapshot_schema_version=2,
        snapshot_data=snapshot_data,
    )
    session.add(snapshot)
    await session.flush()
    for image in await session.scalars(
        select(CharacterImage)
        .where(CharacterImage.character_id == source.id)
        .order_by(CharacterImage.id)
    ):
        session.add(
            CharacterSnapshotImage(
                character_snapshot_id=snapshot.id,
                source_image_id=image.id,
                emotion_tag=image.emotion_tag,
                image_url=image.image_url,
                media_id=image.media_id,
                is_default=image.is_default,
            )
        )
    for asset in await session.scalars(
        select(CharacterAsset)
        .where(CharacterAsset.character_id == source.id)
        .order_by(CharacterAsset.id)
    ):
        session.add(
            CharacterSnapshotAsset(
                character_snapshot_id=snapshot.id,
                source_asset_id=asset.id,
                asset_type=asset.asset_type,
                purpose=asset.purpose,
                file_url=asset.file_url,
                media_id=asset.media_id,
            )
        )
    await session.flush()
    return snapshot


@dataclass(frozen=True)
class SnapshotMediaRow:
    images: list[CharacterSnapshotImage]
    assets: list[CharacterSnapshotAsset]


async def get_snapshot_media(
    session: AsyncSession, snapshot_ids: tuple[UUID, ...]
) -> SnapshotMediaRow:
    images = list(
        await session.scalars(
            select(CharacterSnapshotImage).where(
                CharacterSnapshotImage.character_snapshot_id.in_(snapshot_ids)
            )
        )
    )
    assets = list(
        await session.scalars(
            select(CharacterSnapshotAsset).where(
                CharacterSnapshotAsset.character_snapshot_id.in_(snapshot_ids)
            )
        )
    )
    return SnapshotMediaRow(images, assets)


async def has_snapshot_media_reference(session: AsyncSession, url: str) -> bool:
    image = await session.scalar(
        select(CharacterSnapshotImage.id)
        .where(CharacterSnapshotImage.image_url == url)
        .limit(1)
    )
    asset = await session.scalar(
        select(CharacterSnapshotAsset.id)
        .where(CharacterSnapshotAsset.file_url == url)
        .limit(1)
    )
    return image is not None or asset is not None


async def list_character_snapshots(
    session: AsyncSession, snapshot_ids: tuple[UUID, ...]
) -> list[CharacterSnapshot]:
    return list(
        await session.scalars(
            select(CharacterSnapshot).where(CharacterSnapshot.id.in_(snapshot_ids))
        )
    )


# Durable storage intents; no transaction ownership.


async def get_media(
    session: AsyncSession, media_id: UUID, *, lock: bool = False
) -> CharacterMedia | None:
    stmt = (
        select(CharacterMedia)
        .where(CharacterMedia.id == media_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.scalars(stmt)).one_or_none()


async def get_media_request(
    session: AsyncSession, command: Types.UploadCharacterMediaCommand
) -> CharacterMedia | None:
    return (
        await session.scalars(
            select(CharacterMedia).where(
                CharacterMedia.character_id == command.character_id,
                CharacterMedia.owner_id == command.owner_id,
                CharacterMedia.request_id == command.request_id,
            )
        )
    ).one_or_none()


async def create_media(
    session: AsyncSession, info: Types.CharacterMediaInfo
) -> CharacterMedia:
    entity = CharacterMedia(
        id=info.id,
        character_id=info.character_id,
        owner_id=info.owner_id,
        request_id=info.request_id,
        storage_kind=info.storage_kind,
        storage_id=info.storage_id,
        object_key=info.object_key,
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        original_filename=info.original_filename,
        purpose=info.purpose,
        sha256=info.sha256,
        state=info.state,
        binding=info.binding,
        updated_at=info.updated_at,
    )
    session.add(entity)
    await session.flush()
    return entity


async def set_media_state(session: AsyncSession, media_id: UUID, state: str) -> None:
    await session.execute(
        update(CharacterMedia).where(CharacterMedia.id == media_id).values(state=state)
    )


async def bind_media(session: AsyncSession, media_id: UUID, binding: str) -> None:
    await session.execute(
        update(CharacterMedia)
        .where(CharacterMedia.id == media_id)
        .values(binding=binding)
    )


async def has_media_references(
    session: AsyncSession, media_id: UUID, snapshot_ids: Sequence[UUID] | None = None
) -> bool:
    if snapshot_ids is None:
        statements = [
            select(model.id).where(model.media_id == media_id)
            for model in (
                CharacterImage,
                CharacterAsset,
                CharacterSnapshotImage,
                CharacterSnapshotAsset,
            )
        ]
    else:
        statements = [
            select(model.id)
            .where(model.media_id == media_id)
            .where(model.character_snapshot_id.in_(snapshot_ids))
            for model in (CharacterSnapshotImage, CharacterSnapshotAsset)
        ]
    for stmt in statements:
        if await session.scalar(select(exists(stmt))):
            return True
    return False


@overload
async def get_media_attachment(
    session: AsyncSession, media_id: UUID, kind: Literal["image"]
) -> CharacterImage | None: ...


@overload
async def get_media_attachment(
    session: AsyncSession, media_id: UUID, kind: Literal["asset"]
) -> CharacterAsset | None: ...


async def get_media_attachment(
    session: AsyncSession, media_id: UUID, kind: Literal["image", "asset"]
) -> CharacterImage | CharacterAsset | None:
    if kind == "image":
        return (
            await session.scalars(
                select(CharacterImage).where(CharacterImage.media_id == media_id)
            )
        ).one_or_none()
    return (
        await session.scalars(
            select(CharacterAsset).where(CharacterAsset.media_id == media_id)
        )
    ).one_or_none()


@overload
async def create_media_attachment(
    session: AsyncSession,
    command: Types.CreateCharacterImageCommand,
    media_id: UUID | None,
    kind: Literal["image"],
) -> CharacterImage: ...


@overload
async def create_media_attachment(
    session: AsyncSession,
    command: Types.CreateCharacterAssetCommand,
    media_id: UUID | None,
    kind: Literal["asset"],
) -> CharacterAsset: ...


async def create_media_attachment(
    session: AsyncSession,
    command: Types.CreateCharacterImageCommand | Types.CreateCharacterAssetCommand,
    media_id: UUID | None,
    kind: Literal["image", "asset"],
) -> CharacterImage | CharacterAsset:
    entity: CharacterImage | CharacterAsset
    if kind == "image":
        assert isinstance(command, Types.CreateCharacterImageCommand)
        entity = CharacterImage(
            character_id=command.character_id,
            emotion_tag=command.emotion_tag,
            image_url=command.image_url,
            is_default=command.is_default,
            media_id=media_id,
        )
    else:
        assert isinstance(command, Types.CreateCharacterAssetCommand)
        entity = CharacterAsset(
            character_id=command.character_id,
            asset_type=command.asset_type,
            purpose=command.purpose,
            file_url=command.file_url,
            media_id=media_id,
        )
    session.add(entity)
    await session.flush()
    await session.refresh(entity)
    return entity


async def get_target_for_tag_access(
    session: AsyncSession, target_id: UUID, *, lock: bool = False
) -> Character | None:
    stmt = tag_select(Character).where(Character.id == target_id)
    if lock:
        stmt = stmt.with_for_update()
    return (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).first()


async def list_public_tag_links(
    session: AsyncSession, target_id: UUID
) -> list[CharacterTag]:
    return list(
        await session.scalars(
            tag_select(CharacterTag)
            .where(CharacterTag.character_id == target_id)
            .order_by(
                CharacterTag.sort_order, CharacterTag.created_at, CharacterTag.tag_id
            )
            .execution_options(populate_existing=True)
        )
    )


async def list_internal_tag_links(
    session: AsyncSession, target_id: UUID
) -> list[CharacterInternalTag]:
    return list(
        await session.scalars(
            tag_select(CharacterInternalTag)
            .where(CharacterInternalTag.character_id == target_id)
            .order_by(CharacterInternalTag.created_at, CharacterInternalTag.tag_id)
            .execution_options(populate_existing=True)
        )
    )


async def replace_public_tag_links(
    session: AsyncSession, target_id: UUID, tag_ids: Sequence[UUID], actor_id: UUID
) -> None:
    await session.execute(
        tag_delete(CharacterTag).where(
            CharacterTag.character_id == target_id, CharacterTag.tag_id.not_in(tag_ids)
        )
    )
    for order, tag_id in enumerate(tag_ids):
        stmt = tag_insert(CharacterTag).values(
            character_id=target_id,
            tag_id=tag_id,
            sort_order=order,
            assigned_by=actor_id,
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[CharacterTag.character_id, CharacterTag.tag_id],
                set_={"sort_order": order},
            )
        )


async def remove_public_tag_link(
    session: AsyncSession, target_id: UUID, tag_id: UUID
) -> None:
    await session.execute(
        tag_delete(CharacterTag).where(
            CharacterTag.character_id == target_id, CharacterTag.tag_id == tag_id
        )
    )


async def remove_internal_tag_links(
    session: AsyncSession, target_id: UUID, tag_ids: Sequence[UUID]
) -> None:
    await session.execute(
        tag_delete(CharacterInternalTag).where(
            CharacterInternalTag.character_id == target_id,
            CharacterInternalTag.tag_id.in_(tag_ids),
        )
    )


async def set_internal_tag_link(
    session: AsyncSession,
    target_id: UUID,
    tag_id: UUID,
    source: str,
    actor_id: UUID | None,
) -> None:
    stmt = tag_insert(CharacterInternalTag).values(
        character_id=target_id, tag_id=tag_id, source=source, assigned_by=actor_id
    )
    values = {"source": source, "assigned_by": actor_id, "updated_at": func.now()}
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                CharacterInternalTag.character_id,
                CharacterInternalTag.tag_id,
            ],
            set_=values,
            where=(CharacterInternalTag.source != "admin")
            if source == "system"
            else None,
        )
    )
