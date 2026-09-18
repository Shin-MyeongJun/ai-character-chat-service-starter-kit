# 발행 JSON은 deepcopy로 분리한다. 미디어 비교 manifest는 URL·태그·출처 ID 등을 사용하며 is_default는 포함하지 않는다.
from copy import deepcopy
from typing import cast, overload

from app.db.models import character as character_models
from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types


@overload
def character_entity_to_info(
    entity: character_models.Character,
) -> Types.CharacterInfo: ...


@overload
def character_entity_to_info(entity: None) -> None: ...


def character_entity_to_info(
    entity: character_models.Character | None,
) -> Types.CharacterInfo | None:
    if entity is None:
        return None
    return Types.CharacterInfo(
        id=entity.id,
        owner_id=entity.owner_id,
        name=entity.name,
        description=entity.description,
        persona_prompt=entity.persona_prompt,
        visibility=cast(Types.CharacterVisibilityValue, entity.visibility),
        status=cast(Types.CharacterStatusValue, entity.status),
        default_model_id=entity.default_model_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def character_page_entity_to_info(
    page: Repository.CharacterPageRow,
) -> Types.CharacterPage[Types.CharacterInfo]:
    return Types.CharacterPage(
        items=[character_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@overload
def character_entity_to_prompt_info(
    entity: character_models.Character,
) -> Types.CharacterPromptInfo: ...


@overload
def character_entity_to_prompt_info(entity: None) -> None: ...


def character_entity_to_prompt_info(
    entity: character_models.Character | None,
) -> Types.CharacterPromptInfo | None:
    if entity is None:
        return None
    return Types.CharacterPromptInfo(
        character_id=entity.id,
        persona_prompt=entity.persona_prompt,
        default_model_id=entity.default_model_id,
    )


@overload
def character_image_entity_to_info(
    entity: character_models.CharacterImage,
) -> Types.CharacterImageInfo: ...


@overload
def character_image_entity_to_info(entity: None) -> None: ...


def character_image_entity_to_info(
    entity: character_models.CharacterImage | None,
) -> Types.CharacterImageInfo | None:
    if entity is None:
        return None
    return Types.CharacterImageInfo(
        id=entity.id,
        character_id=entity.character_id,
        emotion_tag=entity.emotion_tag,
        image_url=entity.image_url,
        is_default=entity.is_default,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@overload
def character_asset_entity_to_info(
    entity: character_models.CharacterAsset,
) -> Types.CharacterAssetInfo: ...


@overload
def character_asset_entity_to_info(entity: None) -> None: ...


def character_asset_entity_to_info(
    entity: character_models.CharacterAsset | None,
) -> Types.CharacterAssetInfo | None:
    if entity is None:
        return None
    return Types.CharacterAssetInfo(
        id=entity.id,
        character_id=entity.character_id,
        asset_type=cast(Types.CharacterAssetTypeValue, entity.asset_type),
        purpose=entity.purpose,
        file_url=entity.file_url,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def character_promotion_row_to_info(row) -> Types.CharacterPromotionInfo | None:
    if row is None:
        return None
    return Types.CharacterPromotionInfo(
        character_id=row.character.id,
        name=row.character.name,
        description=row.character.description,
        images=character_images_entities_to_info(row.images),
        assets=character_assets_entities_to_info(row.assets),
    )


def character_images_entities_to_info(entities) -> list[Types.CharacterImageInfo]:
    return [character_image_entity_to_info(entity) for entity in entities]


def character_assets_entities_to_info(entities) -> list[Types.CharacterAssetInfo]:
    return [character_asset_entity_to_info(entity) for entity in entities]


def characters_entities_to_info(entities) -> list[Types.CharacterInfo]:
    return [character_entity_to_info(entity) for entity in entities]


def character_snapshot_entity_to_info(entity) -> Types.CharacterSnapshotInfo:
    return Types.CharacterSnapshotInfo(
        entity.id, entity.character_id, entity.version, deepcopy(entity.snapshot_data)
    )


def snapshot_media_row_to_info(row) -> Types.SnapshotMediaInfo:
    manifest: set[tuple] = {
        ("image", str(i.source_image_id), i.emotion_tag, i.image_url)
        for i in row.images
    }
    manifest.update(
        ("asset", str(a.source_asset_id), a.asset_type, a.purpose, a.file_url)
        for a in row.assets
    )
    return Types.SnapshotMediaInfo(frozenset(manifest))


def character_snapshots_entities_to_info(entities) -> list[Types.CharacterSnapshotInfo]:
    return [character_snapshot_entity_to_info(entity) for entity in entities]
