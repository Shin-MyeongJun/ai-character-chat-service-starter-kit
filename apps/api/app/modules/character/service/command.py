"""Write use cases. Pass a session with no active transaction and a trusted owner_id."""

from typing import get_args
from uuid import UUID

from app.db.models.character import Character as CharacterEntity
from app.modules.character import repository, types
from app.modules.character.mapper import persistence
from sqlalchemy.ext.asyncio import AsyncSession


def _validate_character_profile(
    command: types.CharacterCreate | types.CharacterUpdate,
) -> None:
    # Internal callers bypass HTTP schemas, so enforce these checks in the service.
    if not command.name.strip():
        raise ValueError("Character name must not be blank.")
    if not command.persona_prompt.strip():
        raise ValueError("Character persona prompt must not be blank.")
    if command.visibility not in get_args(types.CharacterVisibilityValue):
        raise ValueError("Invalid character visibility.")


def _validate_character_status(status: types.CharacterStatusValue) -> None:
    if status not in get_args(types.CharacterStatusValue):
        raise ValueError("Invalid character status.")


async def _get_owned_character(
    session: AsyncSession,
    character_id: UUID,
    owner_id: UUID,
) -> CharacterEntity:
    # Serialize writes for a character, including changes to its default image.
    entity = await repository.get_character_by_id_and_owner_id(
        session, character_id, owner_id, for_update=True
    )
    if entity is None:
        raise LookupError("Character not found.")
    return entity


# Character

async def create_character(
    session: AsyncSession,
    command: types.CharacterCreate,
) -> types.CharacterInfo:
    async with session.begin():
        _validate_character_profile(command)
        _validate_character_status(command.status)
        entity = persistence.character_create_to_entity(command)
        entity = await repository.create_character(session, entity)
        return persistence.character_entity_to_info(entity)


async def update_character(
    session: AsyncSession,
    command: types.CharacterUpdate,
) -> types.CharacterInfo:
    async with session.begin():
        entity = await _get_owned_character(
            session, command.character_id, command.owner_id
        )
        _validate_character_profile(command)
        entity = persistence.apply_character_update_to_entity(entity, command)
        entity = await repository.update_character(session, entity)
        return persistence.character_entity_to_info(entity)


async def change_character_status(
    session: AsyncSession,
    command: types.CharacterStatusChange,
) -> types.CharacterInfo:
    """Change status; the caller must authorize any moderation privileges required."""
    async with session.begin():
        entity = await _get_owned_character(
            session, command.character_id, command.owner_id
        )
        _validate_character_status(command.status)
        entity = persistence.apply_character_status_change_to_entity(entity, command)
        entity = await repository.update_character(session, entity)
        return persistence.character_entity_to_info(entity)


async def delete_character(
    session: AsyncSession,
    command: types.CharacterDelete,
) -> None:
    """Delete DB records, including cascading media rows; stored files are untouched."""
    async with session.begin():
        entity = await _get_owned_character(
            session, command.character_id, command.owner_id
        )
        await repository.delete_character(session, entity)


# CharacterImage

async def add_character_image(
    session: AsyncSession,
    command: types.CharacterImageCreate,
) -> types.CharacterImageInfo:
    """TODO: Store the image and resolve its path before persisting metadata."""
    raise NotImplementedError("Character image storage is not implemented yet.")


async def set_default_character_image(
    session: AsyncSession,
    command: types.CharacterImageDefaultSet,
) -> types.CharacterImageInfo:
    async with session.begin():
        await _get_owned_character(session, command.character_id, command.owner_id)
        image = await repository.set_default_character_image(
            session, command.image_id, command.character_id
        )
        if image is None:
            raise LookupError("Character image not found.")
        return persistence.character_image_entity_to_info(image)


async def delete_character_image(
    session: AsyncSession,
    command: types.CharacterImageDelete,
) -> None:
    """Delete image metadata only; physical file cleanup awaits storage integration."""
    async with session.begin():
        await _get_owned_character(session, command.character_id, command.owner_id)
        image = await repository.get_character_image_by_id_and_character_id(
            session, command.image_id, command.character_id
        )
        if image is None:
            raise LookupError("Character image not found.")
        await repository.delete_character_image(session, image)


# CharacterAsset

async def add_character_asset(
    session: AsyncSession,
    command: types.CharacterAssetCreate,
) -> types.CharacterAssetInfo:
    """TODO: Store the asset and resolve its path before persisting metadata."""
    raise NotImplementedError("Character asset storage is not implemented yet.")


async def delete_character_asset(
    session: AsyncSession,
    command: types.CharacterAssetDelete,
) -> None:
    """Delete asset metadata only; physical file cleanup awaits storage integration."""
    async with session.begin():
        await _get_owned_character(session, command.character_id, command.owner_id)
        asset = await repository.get_character_asset_by_id_and_character_id(
            session, command.asset_id, command.character_id
        )
        if asset is None:
            raise LookupError("Character asset not found.")
        await repository.delete_character_asset(session, asset)
