"""Write use cases; authorization uses detached values and writes stay in repository."""

from typing import get_args
from uuid import UUID

from app.db.transaction import use_case_transaction
from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types
from app.modules.content.character.mapper import persistence as PersistenceMapper
from sqlalchemy.ext.asyncio import AsyncSession


def _validate_character_profile(
    command: Types.CreateCharacterCommand | Types.UpdateCharacterCommand,
) -> None:
    # Internal callers bypass HTTP schemas, so enforce these checks in the service.
    if not command.name.strip():
        raise ValueError("Character name must not be blank.")
    if not command.persona_prompt.strip():
        raise ValueError("Character persona prompt must not be blank.")
    if command.visibility not in get_args(Types.CharacterVisibilityValue):
        raise ValueError("Invalid character visibility.")


def _validate_character_status(status: Types.CharacterStatusValue) -> None:
    if status not in get_args(Types.CharacterStatusValue):
        raise ValueError("Invalid character status.")


async def _get_owned_character(
    session: AsyncSession, character_id: UUID, owner_id: UUID
) -> Types.CharacterInfo:
    row = await Repository.get_character_by_id_and_owner_id(
        session, character_id, owner_id, for_update=True
    )
    info = PersistenceMapper.character_entity_to_info(row)
    if info is None:
        raise LookupError("Character not found.")
    return info


async def create_character(
    session: AsyncSession, command: Types.CreateCharacterCommand
) -> Types.CharacterInfo:
    async with use_case_transaction(session):
        _validate_character_profile(command)
        _validate_character_status(command.status)
        row = await Repository.create_character_command(session, command)
        return PersistenceMapper.character_entity_to_info(row)


async def update_character(
    session: AsyncSession, command: Types.UpdateCharacterCommand
) -> Types.CharacterInfo:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        _validate_character_profile(command)
        row = await Repository.update_character_command(session, command)
        return PersistenceMapper.character_entity_to_info(row)


async def change_character_status(
    session: AsyncSession, command: Types.ChangeCharacterStatusCommand
) -> Types.CharacterInfo:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        _validate_character_status(command.status)
        row = await Repository.change_character_status_command(session, command)
        return PersistenceMapper.character_entity_to_info(row)


async def delete_character(
    session: AsyncSession, command: Types.DeleteCharacterCommand
) -> None:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        await Repository.delete_character_command(session, command)


async def add_character_image(
    session: AsyncSession, command: Types.CreateCharacterImageCommand
) -> Types.CharacterImageInfo:
    from app.modules.content.character.service.media import _attach_character_media

    if not command.emotion_tag.strip():
        raise ValueError("Emotion tag must not be blank.")
    async with use_case_transaction(session):
        return await _attach_character_media(session, command, "image")


async def delete_character_image(
    session: AsyncSession, command: Types.DeleteCharacterImageCommand
) -> None:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        row = await Repository.get_character_image_by_id_and_character_id(
            session, command.image_id, command.character_id
        )
        info = PersistenceMapper.character_image_entity_to_info(row)
        if info is None:
            raise LookupError("Character image not found.")
        await Repository.delete_character_image_command(session, command)


async def add_character_asset(
    session: AsyncSession, command: Types.CreateCharacterAssetCommand
) -> Types.CharacterAssetInfo:
    from app.modules.content.character.service.media import _attach_character_media

    if (
        command.asset_type not in get_args(Types.CharacterAssetTypeValue)
        or not command.purpose.strip()
    ):
        raise ValueError("Invalid asset metadata.")
    async with use_case_transaction(session):
        return await _attach_character_media(session, command, "asset")


async def delete_character_asset(
    session: AsyncSession, command: Types.DeleteCharacterAssetCommand
) -> None:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        row = await Repository.get_character_asset_by_id_and_character_id(
            session, command.asset_id, command.character_id
        )
        info = PersistenceMapper.character_asset_entity_to_info(row)
        if info is None:
            raise LookupError("Character asset not found.")
        await Repository.delete_character_asset_command(session, command)


async def set_default_character_image(
    session: AsyncSession, command: Types.SetDefaultCharacterImageCommand
) -> Types.CharacterImageInfo:
    async with use_case_transaction(session):
        await _get_owned_character(session, command.character_id, command.owner_id)
        row = await Repository.set_default_character_image(
            session, command.image_id, command.character_id
        )
        info = PersistenceMapper.character_image_entity_to_info(row)
        if info is None:
            raise LookupError("Character image not found.")
        return info


async def freeze_character(
    session: AsyncSession, command: Types.FreezeCharacterCommand
) -> Types.CharacterSnapshotInfo:
    async with use_case_transaction(session):
        source = await _get_owned_character(
            session, command.character_id, command.owner_id
        )
        row = await Repository.freeze_character(session, source)
        return PersistenceMapper.character_snapshot_entity_to_info(row)
