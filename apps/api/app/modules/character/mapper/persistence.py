from typing import cast

from app.db.models import character as character_models
from app.modules.character import types

# Command type -> SQLAlchemy entity

def character_create_to_entity(
    command: types.CharacterCreate,
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


def apply_character_update_to_entity(
    entity: character_models.Character,
    command: types.CharacterUpdate,
) -> character_models.Character:
    entity.name = command.name
    entity.description = command.description
    entity.persona_prompt = command.persona_prompt
    entity.visibility = command.visibility
    entity.default_model_id = command.default_model_id
    return entity


def apply_character_status_change_to_entity(
    entity: character_models.Character,
    command: types.CharacterStatusChange,
) -> character_models.Character:
    entity.status = command.status
    return entity


def character_image_create_to_entity(
    command: types.CharacterImageCreate,
) -> character_models.CharacterImage:
    return character_models.CharacterImage(
        character_id=command.character_id,
        emotion_tag=command.emotion_tag,
        image_url=command.image_url,
        is_default=command.is_default,
    )


def character_asset_create_to_entity(
    command: types.CharacterAssetCreate,
) -> character_models.CharacterAsset:
    return character_models.CharacterAsset(
        character_id=command.character_id,
        asset_type=command.asset_type,
        purpose=command.purpose,
        file_url=command.file_url,
    )


# SQLAlchemy entity -> result type


def character_entity_to_info(
    entity: character_models.Character,
) -> types.CharacterInfo:
    return types.CharacterInfo(
        id=entity.id,
        owner_id=entity.owner_id,
        name=entity.name,
        description=entity.description,
        persona_prompt=entity.persona_prompt,
        visibility=cast(types.CharacterVisibilityValue, entity.visibility),
        status=cast(types.CharacterStatusValue, entity.status),
        default_model_id=entity.default_model_id,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def character_page_entity_to_info(
    page: types.CharacterPage[character_models.Character],
) -> types.CharacterPage[types.CharacterInfo]:
    return types.CharacterPage(
        items=[character_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def character_entity_to_prompt_info(
    entity: character_models.Character,
) -> types.CharacterPromptInfo:
    return types.CharacterPromptInfo(
        character_id=entity.id,
        persona_prompt=entity.persona_prompt,
        default_model_id=entity.default_model_id,
    )


def character_image_entity_to_info(
    entity: character_models.CharacterImage,
) -> types.CharacterImageInfo:
    return types.CharacterImageInfo(
        id=entity.id,
        character_id=entity.character_id,
        emotion_tag=entity.emotion_tag,
        image_url=entity.image_url,
        is_default=entity.is_default,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def character_asset_entity_to_info(
    entity: character_models.CharacterAsset,
) -> types.CharacterAssetInfo:
    return types.CharacterAssetInfo(
        id=entity.id,
        character_id=entity.character_id,
        asset_type=cast(types.CharacterAssetTypeValue, entity.asset_type),
        purpose=entity.purpose,
        file_url=entity.file_url,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )
