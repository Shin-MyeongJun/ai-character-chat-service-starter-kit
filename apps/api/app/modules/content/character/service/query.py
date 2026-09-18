# owner가 없는 전역·프롬프트·미디어 조회는 호출자가 인가를 마쳐야 한다. 함수 이름의 public과 인가를 혼동하지 않는다.
# get_owned_characters는 요청 개수와 조회 개수를 비교하며 발행 시 ID 순 잠금을 요청할 수 있다.
"""Read use cases shared by HTTP routers and other application modules.

Return Result dataclasses, never ORM entities or HTTP schemas. Singular reads
return None when absent; collection reads return empty items. The caller owns
authorization and session/transaction lifetime; these functions do not explicitly
begin, commit, or roll back transactions. SELECT may autobegin a transaction
and honors the caller's session autoflush setting for pending changes.
"""

from typing import get_args

from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types
from app.modules.content.character.mapper import persistence as PersistenceMapper
from sqlalchemy.ext.asyncio import AsyncSession


async def list_characters(
    session: AsyncSession, command: Types.ListCharactersCommand
) -> Types.CharacterPage[Types.CharacterInfo]:
    """List all characters, regardless of owner, visibility, or moderation status."""
    cursor = command.cursor
    limit = command.limit
    page = await Repository.list_characters(session, cursor=cursor, limit=limit)
    return PersistenceMapper.character_page_entity_to_info(page)


async def list_characters_by_owner_id(
    session: AsyncSession, command: Types.ListCharactersByOwnerIdCommand
) -> Types.CharacterPage[Types.CharacterInfo]:
    owner_id = command.owner_id
    cursor = command.cursor
    limit = command.limit
    page = await Repository.list_characters_by_owner_id(
        session, owner_id, cursor=cursor, limit=limit
    )
    return PersistenceMapper.character_page_entity_to_info(page)


async def get_character_by_id(
    session: AsyncSession, command: Types.GetCharacterByIdCommand
) -> Types.CharacterInfo | None:
    character_id = command.character_id
    entity = await Repository.get_character_by_id(session, character_id)
    return PersistenceMapper.character_entity_to_info(entity)


async def get_character_by_id_and_owner_id(
    session: AsyncSession, command: Types.GetCharacterByIdAndOwnerIdCommand
) -> Types.CharacterInfo | None:
    """Return None both for an absent character and for an owner mismatch."""
    character_id = command.character_id
    owner_id = command.owner_id
    entity = await Repository.get_character_by_id_and_owner_id(
        session, character_id, owner_id
    )
    return PersistenceMapper.character_entity_to_info(entity)


async def get_character_image(
    session: AsyncSession, command: Types.GetCharacterImageCommand
) -> Types.CharacterImageInfo | None:
    character_id = command.character_id
    image_id = command.image_id
    entity = await Repository.get_character_image_by_id_and_character_id(
        session, image_id, character_id
    )
    return PersistenceMapper.character_image_entity_to_info(entity)


async def get_character_image_by_emotion_tag(
    session: AsyncSession, command: Types.GetCharacterImageByEmotionTagCommand
) -> Types.CharacterImageInfo | None:
    """Match an exact emotion tag; missing tags do not silently use a default image."""
    character_id = command.character_id
    emotion_tag = command.emotion_tag
    entity = await Repository.get_character_image_by_emotion_tag(
        session, character_id, emotion_tag
    )
    return PersistenceMapper.character_image_entity_to_info(entity)


async def get_default_character_image(
    session: AsyncSession, command: Types.GetDefaultCharacterImageCommand
) -> Types.CharacterImageInfo | None:
    character_id = command.character_id
    entity = await Repository.get_default_character_image(session, character_id)
    return PersistenceMapper.character_image_entity_to_info(entity)


async def list_character_images(
    session: AsyncSession, command: Types.ListCharacterImagesCommand
) -> list[Types.CharacterImageInfo]:
    character_id = command.character_id
    entities = await Repository.list_character_images(session, character_id)
    return PersistenceMapper.character_images_entities_to_info(entities)


async def get_character_asset(
    session: AsyncSession, command: Types.GetCharacterAssetCommand
) -> Types.CharacterAssetInfo | None:
    character_id = command.character_id
    asset_id = command.asset_id
    entity = await Repository.get_character_asset_by_id_and_character_id(
        session, asset_id, character_id
    )
    return PersistenceMapper.character_asset_entity_to_info(entity)


async def list_character_assets(
    session: AsyncSession, command: Types.ListCharacterAssetsCommand
) -> list[Types.CharacterAssetInfo]:
    character_id = command.character_id
    asset_type = command.asset_type
    if asset_type is None:
        entities = await Repository.list_character_assets(session, character_id)
    else:
        if asset_type not in get_args(Types.CharacterAssetTypeValue):
            raise ValueError("Invalid character asset type.")
        entities = await Repository.list_character_assets_by_type(
            session, character_id, asset_type
        )
    return PersistenceMapper.character_assets_entities_to_info(entities)


async def get_character_prompt(
    session: AsyncSession, command: Types.GetCharacterPromptCommand
) -> Types.CharacterPromptInfo | None:
    character_id = command.character_id
    entity = await Repository.get_character_by_id(session, character_id)
    return PersistenceMapper.character_entity_to_prompt_info(entity)


async def get_character_promotion(
    session: AsyncSession, command: Types.GetCharacterPromotionCommand
) -> Types.CharacterPromotionInfo | None:
    """Collect description and all media for one authorized character."""
    character_id = command.character_id
    row = await Repository.get_character_promotion(session, character_id)
    return PersistenceMapper.character_promotion_row_to_info(row)


async def get_owned_characters(
    session: AsyncSession, command: Types.GetOwnedCharactersCommand
) -> list[Types.CharacterInfo]:
    rows = await Repository.list_owned_characters(
        session, command.ids, command.owner_id, lock=command.lock
    )
    infos = PersistenceMapper.characters_entities_to_info(rows)
    if len(infos) != len(command.ids):
        raise LookupError("Owned component not found.")
    return infos


async def get_snapshot_media(
    session: AsyncSession, command: Types.GetSnapshotMediaCommand
) -> Types.SnapshotMediaInfo:
    row = await Repository.get_snapshot_media(session, command.snapshot_ids)
    return PersistenceMapper.snapshot_media_row_to_info(row)


async def check_media_reference(
    session: AsyncSession, command: Types.CheckMediaReferenceCommand
) -> Types.MediaReferenceInfo:
    return Types.MediaReferenceInfo(
        await Repository.has_snapshot_media_reference(session, command.url)
    )


async def get_character_snapshots(
    session: AsyncSession, command: Types.GetCharacterSnapshotsCommand
) -> list[Types.CharacterSnapshotInfo]:
    rows = await Repository.list_character_snapshots(session, command.snapshot_ids)
    return PersistenceMapper.character_snapshots_entities_to_info(rows)
