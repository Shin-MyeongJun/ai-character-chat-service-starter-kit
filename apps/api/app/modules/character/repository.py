from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import (
    Character,
    CharacterAsset,
    CharacterImage,
    CharacterVisibility,
)
from app.db.pagination import fetch_cursor_page
from app.modules.character.types import CharacterCursor, CharacterPage

DEFAULT_CHARACTER_LIST_LIMIT = 50
MAX_CHARACTER_LIST_LIMIT = 100


async def _fetch_character_page(
    session: AsyncSession,
    stmt: Select[tuple[Character]],
    *,
    cursor: CharacterCursor | None,
    limit: int,
) -> CharacterPage[Character]:
    return await fetch_cursor_page(
        session, stmt,
        created_at=Character.created_at,
        id_column=Character.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_CHARACTER_LIST_LIMIT,
        cursor_factory=CharacterCursor,
        page_factory=CharacterPage,
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
) -> CharacterPage[Character]:
    # Unrestricted collection; public visibility/moderation policies belong to callers.
    return await _fetch_character_page(
        session, select(Character), cursor=cursor, limit=limit
    )


async def list_characters_by_owner_id(
    session: AsyncSession,
    owner_id: UUID,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPage[Character]:
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
) -> CharacterPage[Character]:
    stmt = select(Character).where(
        Character.visibility == CharacterVisibility.PUBLIC.value
    )

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def list_characters_by_status(
    session: AsyncSession,
    status: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPage[Character]:
    stmt = select(Character).where(Character.status == status)

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def list_characters_by_visibility(
    session: AsyncSession,
    visibility: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPage[Character]:
    stmt = select(Character).where(Character.visibility == visibility)

    return await _fetch_character_page(session, stmt, cursor=cursor, limit=limit)


async def search_characters_by_name(
    session: AsyncSession,
    keyword: str,
    cursor: CharacterCursor | None = None,
    limit: int = DEFAULT_CHARACTER_LIST_LIMIT,
) -> CharacterPage[Character]:
    keyword = keyword.strip()
    if not keyword:
        return CharacterPage(items=[], next_cursor=None)

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
