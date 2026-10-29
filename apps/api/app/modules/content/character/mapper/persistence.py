# 발행 JSON은 deepcopy로 분리한다. 미디어 비교 manifest는 URL·태그·출처 ID 등을 사용하며 is_default는 포함하지 않는다.
from collections.abc import Iterable
from copy import deepcopy
from typing import cast, overload

from app.db.models import character as character_models
from app.db.models.snapshot.character import CharacterSnapshot
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
        # The model's CHECK constraints restrict these stored strings to the literals.
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
        # CharacterAsset's CHECK constraint enforces the allowed storage values.
        asset_type=cast(Types.CharacterAssetTypeValue, entity.asset_type),
        purpose=entity.purpose,
        file_url=entity.file_url,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def character_promotion_row_to_info(
    row: Repository.CharacterPromotionRow | None,
) -> Types.CharacterPromotionInfo | None:
    if row is None:
        return None
    return Types.CharacterPromotionInfo(
        character_id=row.character.id,
        name=row.character.name,
        description=row.character.description,
        images=character_images_entities_to_info(row.images),
        assets=character_assets_entities_to_info(row.assets),
    )


def character_images_entities_to_info(
    entities: Iterable[character_models.CharacterImage],
) -> list[Types.CharacterImageInfo]:
    return [character_image_entity_to_info(entity) for entity in entities]


def character_assets_entities_to_info(
    entities: Iterable[character_models.CharacterAsset],
) -> list[Types.CharacterAssetInfo]:
    return [character_asset_entity_to_info(entity) for entity in entities]


def characters_entities_to_info(
    entities: Iterable[character_models.Character],
) -> list[Types.CharacterInfo]:
    return [character_entity_to_info(entity) for entity in entities]


def character_snapshot_entity_to_info(
    entity: CharacterSnapshot,
) -> Types.CharacterSnapshotInfo:
    return Types.CharacterSnapshotInfo(
        id=entity.id,
        character_id=entity.character_id,
        version=entity.version,
        snapshot_data=deepcopy(entity.snapshot_data),
    )


def snapshot_media_row_to_info(
    row: Repository.SnapshotMediaRow,
) -> Types.SnapshotMediaInfo:
    manifest: set[Types.SnapshotMediaManifestItem] = {
        ("image", str(image.source_image_id), image.emotion_tag, image.image_url)
        for image in row.images
    }
    manifest.update(
        (
            "asset",
            str(asset.source_asset_id),
            asset.asset_type,
            asset.purpose,
            asset.file_url,
        )
        for asset in row.assets
    )
    return Types.SnapshotMediaInfo(frozenset(manifest))


def character_snapshots_entities_to_info(
    entities: Iterable[CharacterSnapshot],
) -> list[Types.CharacterSnapshotInfo]:
    return [character_snapshot_entity_to_info(entity) for entity in entities]
