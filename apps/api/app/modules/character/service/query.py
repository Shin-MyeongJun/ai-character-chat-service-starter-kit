"""Read use cases shared by HTTP routers and other application modules.

Return Result dataclasses, never ORM entities or HTTP schemas. Singular reads
return None when absent; collection reads return empty items. The caller owns
authorization and session/transaction lifetime; these functions do not explicitly
begin, commit, or roll back transactions. SELECT may autobegin a transaction
and honors the caller's session autoflush setting for pending changes.
"""

from typing import get_args
from uuid import UUID

from app.modules.character import repository, types
from app.modules.character.mapper import persistence
from sqlalchemy.ext.asyncio import AsyncSession

# Router-oriented queries
# Keep these sections together for now; split by use case when this file grows.
# IMPORTANT: these are authorized management reads, not a public catalog API.
# Full CharacterInfo includes persona_prompt and private/draft records. The caller
# must authorize access and derive owner_id from a trusted identity/context.


async def list_characters(
    session: AsyncSession,
    *,
    cursor: types.CharacterCursor | None = None,
    limit: int = repository.DEFAULT_CHARACTER_LIST_LIMIT,
) -> types.CharacterPage[types.CharacterInfo]:
    """List all characters, regardless of owner, visibility, or moderation status."""
    page = await repository.list_characters(session, cursor=cursor, limit=limit)
    return persistence.character_page_entity_to_info(page)


async def list_characters_by_owner_id(
    session: AsyncSession,
    *,
    owner_id: UUID,
    cursor: types.CharacterCursor | None = None,
    limit: int = repository.DEFAULT_CHARACTER_LIST_LIMIT,
) -> types.CharacterPage[types.CharacterInfo]:
    page = await repository.list_characters_by_owner_id(
        session, owner_id, cursor=cursor, limit=limit
    )
    return persistence.character_page_entity_to_info(page)


# Additional detail reads support router detail/edit views without exposing ORM.
async def get_character_by_id(
    session: AsyncSession,
    *,
    character_id: UUID,
) -> types.CharacterInfo | None:
    entity = await repository.get_character_by_id(session, character_id)
    if entity is None:
        return None
    return persistence.character_entity_to_info(entity)


async def get_character_by_id_and_owner_id(
    session: AsyncSession,
    *,
    character_id: UUID,
    owner_id: UUID,
) -> types.CharacterInfo | None:
    """Return None both for an absent character and for an owner mismatch."""
    entity = await repository.get_character_by_id_and_owner_id(
        session, character_id, owner_id
    )
    if entity is None:
        return None
    return persistence.character_entity_to_info(entity)


# TODO: Implement router search/filter queries after search requirements and
# supporting metadata are defined (keyword, tags, visibility/status, sorting).
# Define public catalog visibility/moderation rules and its response fields then.
# Group conditions in a Query/Filter input type when they need reuse; pagination
# cursors must agree with the selected filters and sort order.


# Queries for other modules (chat, conversation, character presentation, etc.)
# Internal use alone does not grant access: callers must authorize the character.
# A missing parent and an existing parent with no media both yield [] in media
# lists. Use a character detail read if the caller must distinguish those cases.


async def get_character_image(
    session: AsyncSession,
    *,
    character_id: UUID,
    image_id: UUID,
) -> types.CharacterImageInfo | None:
    # Always scope child IDs to the character to avoid returning unrelated media.
    entity = await repository.get_character_image_by_id_and_character_id(
        session, image_id, character_id
    )
    if entity is None:
        return None
    return persistence.character_image_entity_to_info(entity)


async def get_character_image_by_emotion_tag(
    session: AsyncSession,
    *,
    character_id: UUID,
    emotion_tag: str,
) -> types.CharacterImageInfo | None:
    """Match an exact emotion tag; missing tags do not silently use a default image."""
    entity = await repository.get_character_image_by_emotion_tag(
        session, character_id, emotion_tag
    )
    if entity is None:
        return None
    return persistence.character_image_entity_to_info(entity)


async def get_default_character_image(
    session: AsyncSession,
    *,
    character_id: UUID,
) -> types.CharacterImageInfo | None:
    # Additional read: the caller can explicitly choose a fallback for missing tags.
    entity = await repository.get_default_character_image(session, character_id)
    if entity is None:
        return None
    return persistence.character_image_entity_to_info(entity)


async def list_character_images(
    session: AsyncSession,
    *,
    character_id: UUID,
) -> list[types.CharacterImageInfo]:
    entities = await repository.list_character_images(session, character_id)
    return [persistence.character_image_entity_to_info(entity) for entity in entities]


async def get_character_asset(
    session: AsyncSession,
    *,
    character_id: UUID,
    asset_id: UUID,
) -> types.CharacterAssetInfo | None:
    entity = await repository.get_character_asset_by_id_and_character_id(
        session, asset_id, character_id
    )
    if entity is None:
        return None
    return persistence.character_asset_entity_to_info(entity)


async def list_character_assets(
    session: AsyncSession,
    *,
    character_id: UUID,
    asset_type: types.CharacterAssetTypeValue | None = None,
) -> list[types.CharacterAssetInfo]:
    # Optional type selection reuses the existing repository filter for chat/media.
    if asset_type is None:
        entities = await repository.list_character_assets(session, character_id)
    else:
        # Literal annotations alone do not validate calls from other Python modules.
        if asset_type not in get_args(types.CharacterAssetTypeValue):
            raise ValueError("Invalid character asset type.")
        entities = await repository.list_character_assets_by_type(
            session, character_id, asset_type
        )
    return [persistence.character_asset_entity_to_info(entity) for entity in entities]


async def get_character_prompt(
    session: AsyncSession,
    *,
    character_id: UUID,
) -> types.CharacterPromptInfo | None:
    entity = await repository.get_character_by_id(session, character_id)
    if entity is None:
        return None
    return persistence.character_entity_to_prompt_info(entity)


async def get_character_promotion(
    session: AsyncSession,
    *,
    character_id: UUID,
) -> types.CharacterPromotionInfo | None:
    """Collect description and all media for one authorized character."""
    entity = await repository.get_character_by_id(session, character_id)
    if entity is None:
        return None

    # Do not run concurrent operations on the same AsyncSession. These three
    # reads are not a guaranteed snapshot at READ COMMITTED; a caller requiring
    # that guarantee must choose an appropriate transaction isolation level.
    images = await list_character_images(session, character_id=character_id)
    assets = await list_character_assets(session, character_id=character_id)
    # Includes every asset purpose; public media selection awaits product policy.
    # For future list previews, add batched loading instead of calling this per row.
    return types.CharacterPromotionInfo(
        character_id=entity.id,
        name=entity.name,
        description=entity.description,
        images=images,
        assets=assets,
    )
