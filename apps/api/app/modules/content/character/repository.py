from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import character as character_models
from app.db.models.character import (
    Character,
    CharacterAsset,
    CharacterImage,
    CharacterVisibility,
)
from app.db.models.snapshot.character import (
    CharacterSnapshot,
    CharacterSnapshotAsset,
    CharacterSnapshotImage,
)
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
):
    entity = _create_character_entity(command)
    return await create_character(session, entity)


async def update_character_command(
    session: AsyncSession, command: Types.UpdateCharacterCommand
):
    entity = await get_character_by_id_and_owner_id(
        session, command.character_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_character_update(entity, command)
    return await update_character(session, entity)


async def change_character_status_command(
    session: AsyncSession, command: Types.ChangeCharacterStatusCommand
):
    entity = await get_character_by_id_and_owner_id(
        session, command.character_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_character_status_change(entity, command)
    return await update_character(session, entity)


async def delete_character_command(
    session: AsyncSession, command: Types.DeleteCharacterCommand
):
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
    session: AsyncSession, ids: tuple[UUID, ...], owner_id: UUID, *, lock=False
):
    stmt = (
        select(Character)
        .where(Character.id.in_(ids), Character.owner_id == owner_id)
        .order_by(Character.id)
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list(await session.scalars(stmt))


async def next_version(session, cls, column, source_id):
    return (
        await session.scalar(select(func.max(cls.version)).where(column == source_id))
        or 0
    ) + 1


async def freeze_character(session, source):
    snapshot = CharacterSnapshot(
        id=uuid4(),
        character_id=source.id,
        version=await next_version(
            session, CharacterSnapshot, CharacterSnapshot.character_id, source.id
        ),
        snapshot_schema_version=2,
        snapshot_data={
            key: getattr(source, key)
            for key in ("name", "description", "persona_prompt")
        },
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
            )
        )
    await session.flush()
    return snapshot


@dataclass(frozen=True)
class SnapshotMediaRow:
    images: list[CharacterSnapshotImage]
    assets: list[CharacterSnapshotAsset]


async def get_snapshot_media(session, snapshot_ids) -> SnapshotMediaRow:
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


async def has_snapshot_media_reference(session, url) -> bool:
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


async def list_character_snapshots(session, snapshot_ids):
    return list(
        await session.scalars(
            select(CharacterSnapshot).where(CharacterSnapshot.id.in_(snapshot_ids))
        )
    )
