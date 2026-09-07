"""Lorebook write use cases.

Pass an AsyncSession with no active transaction and a trusted owner_id. Each
function owns its transaction and maps ORM entities before the commit expires
them.
"""

import json
from typing import get_args
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lorebook import Lorebook, LorebookEntry
from app.modules.lorebook import constraints, matching, repository, types
from app.modules.lorebook.mapper import persistence


def _validate_lorebook_profile(
    command: types.LorebookCreate | types.LorebookUpdate,
) -> None:
    if not command.title.strip():
        raise ValueError("Lorebook title must not be blank.")
    if len(command.title) > constraints.LOREBOOK_TITLE_MAX_LENGTH:
        raise ValueError("Lorebook title is too long.")
    if (
        command.description is not None
        and len(command.description) > constraints.LOREBOOK_DESCRIPTION_MAX_LENGTH
    ):
        raise ValueError("Lorebook description is too long.")
    if command.visibility not in get_args(types.LorebookVisibilityValue):
        raise ValueError("Invalid lorebook visibility.")


def _validate_lorebook_status(status: types.LorebookStatusValue) -> None:
    if status not in get_args(types.LorebookStatusValue):
        raise ValueError("Invalid lorebook status.")


def _validate_lorebook_entry(
    command: types.LorebookEntryCreate | types.LorebookEntryUpdate,
) -> None:
    if not command.content.strip():
        raise ValueError("Lorebook entry content must not be blank.")
    if len(command.content) > constraints.ENTRY_CONTENT_MAX_LENGTH:
        raise ValueError("Lorebook entry content is too long.")
    if command.title is not None and not command.title.strip():
        raise ValueError("Lorebook entry title must not be blank when provided.")
    if (
        command.title is not None
        and len(command.title) > constraints.ENTRY_TITLE_MAX_LENGTH
    ):
        raise ValueError("Lorebook entry title is too long.")
    enum_values = (
        (command.entry_type, types.LorebookEntryTypeValue, "entry type"),
        (
            command.activation_type,
            types.LorebookEntryActivationTypeValue,
            "activation type",
        ),
        (command.match_mode, types.LorebookEntryMatchModeValue, "match mode"),
        (command.placement, types.LorebookEntryPlacementValue, "placement"),
    )
    for value, value_type, label in enum_values:
        if value not in get_args(value_type):
            raise ValueError(f"Invalid lorebook entry {label}.")
    if not (
        constraints.POSTGRES_INTEGER_MIN
        <= command.priority
        <= constraints.POSTGRES_INTEGER_MAX
    ):
        raise ValueError("Lorebook entry priority is outside the database range.")
    if command.token_budget is not None and not (
        0 <= command.token_budget <= constraints.POSTGRES_INTEGER_MAX
    ):
        raise ValueError("Lorebook entry token budget is outside the database range.")
    if (
        command.activation_type == "keyword"
        and command.is_enabled
        and not command.key_triggers
    ):
        raise ValueError("Keyword entries require at least one trigger.")
    if command.key_triggers is not None:
        if len(command.key_triggers) > constraints.ENTRY_TRIGGER_MAX_COUNT:
            raise ValueError("Lorebook entry has too many triggers.")
        for trigger in command.key_triggers:
            if not trigger.strip():
                raise ValueError("Lorebook entry triggers must not be blank.")
            if len(trigger) > constraints.ENTRY_TRIGGER_MAX_LENGTH:
                raise ValueError("Lorebook entry trigger is too long.")
            if command.match_mode == "regex":
                matching.validate_regex(trigger)
    if command.metadata is not None:
        try:
            serialized_metadata = json.dumps(command.metadata, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Lorebook entry metadata must be JSON serializable."
            ) from exc
        if (
            len(serialized_metadata.encode("utf-8"))
            > constraints.ENTRY_METADATA_MAX_BYTES
        ):
            raise ValueError("Lorebook entry metadata is too large.")


async def _get_owned_lorebook(
    session: AsyncSession,
    lorebook_id: UUID,
    owner_id: UUID,
) -> Lorebook:
    entity = await repository.get_lorebook_by_id_and_owner_id(
        session,
        lorebook_id,
        owner_id,
        for_update=True,
    )
    if entity is None:
        raise LookupError("Lorebook not found.")
    return entity


async def create_lorebook(
    session: AsyncSession,
    command: types.LorebookCreate,
) -> types.LorebookInfo:
    async with session.begin():
        _validate_lorebook_profile(command)
        _validate_lorebook_status(command.status)
        entity = persistence.lorebook_create_to_entity(command)
        entity = await repository.create_lorebook(session, entity)
        return persistence.lorebook_entity_to_info(entity)


async def update_lorebook(
    session: AsyncSession,
    command: types.LorebookUpdate,
) -> types.LorebookInfo:
    async with session.begin():
        entity = await _get_owned_lorebook(
            session, command.lorebook_id, command.owner_id
        )
        _validate_lorebook_profile(command)
        entity = persistence.apply_lorebook_update_to_entity(entity, command)
        entity = await repository.update_lorebook(session, entity)
        return persistence.lorebook_entity_to_info(entity)


async def change_lorebook_status(
    session: AsyncSession,
    command: types.LorebookStatusChange,
) -> types.LorebookInfo:
    """Change status after the caller performs any moderator authorization."""
    async with session.begin():
        entity = await _get_owned_lorebook(
            session, command.lorebook_id, command.owner_id
        )
        _validate_lorebook_status(command.status)
        entity = persistence.apply_lorebook_status_change_to_entity(entity, command)
        entity = await repository.update_lorebook(session, entity)
        return persistence.lorebook_entity_to_info(entity)


async def delete_lorebook(
    session: AsyncSession,
    command: types.LorebookDelete,
) -> None:
    async with session.begin():
        entity = await _get_owned_lorebook(
            session, command.lorebook_id, command.owner_id
        )
        await repository.delete_lorebook(session, entity)


async def create_lorebook_entry(
    session: AsyncSession,
    command: types.LorebookEntryCreate,
) -> types.LorebookEntryInfo:
    async with session.begin():
        _validate_lorebook_entry(command)
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        entity = persistence.lorebook_entry_create_to_entity(command)
        entity = await repository.create_lorebook_entry(session, entity)
        return persistence.lorebook_entry_entity_to_info(entity)


async def update_lorebook_entry(
    session: AsyncSession,
    command: types.LorebookEntryUpdate,
) -> types.LorebookEntryInfo:
    async with session.begin():
        _validate_lorebook_entry(command)
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        entity = await repository.get_lorebook_entry(
            session,
            command.entry_id,
            command.lorebook_id,
            for_update=True,
        )
        if entity is None:
            raise LookupError("Lorebook entry not found.")
        entity = persistence.apply_lorebook_entry_update_to_entity(entity, command)
        entity = await repository.update_lorebook_entry(session, entity)
        return persistence.lorebook_entry_entity_to_info(entity)


async def delete_lorebook_entry(
    session: AsyncSession,
    command: types.LorebookEntryDelete,
) -> None:
    async with session.begin():
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        entity: LorebookEntry | None = await repository.get_lorebook_entry(
            session,
            command.entry_id,
            command.lorebook_id,
            for_update=True,
        )
        if entity is None:
            raise LookupError("Lorebook entry not found.")
        await repository.delete_lorebook_entry(session, entity)
