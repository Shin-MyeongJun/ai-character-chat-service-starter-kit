"""Write use cases; authorization uses detached values and writes stay in repository."""

import json
from typing import get_args
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.modules.content.lorebook import constraints
from app.modules.content.lorebook import repository as Repository
from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.mapper import persistence as PersistenceMapper
from app.modules.content.lorebook.service.util import matching as MatchingServiceUtil


def _validate_lorebook_profile(
    command: Types.CreateLorebookCommand | Types.UpdateLorebookCommand,
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
    if command.visibility not in get_args(Types.LorebookVisibilityValue):
        raise ValueError("Invalid lorebook visibility.")


def _validate_lorebook_status(status: Types.LorebookStatusValue) -> None:
    if status not in get_args(Types.LorebookStatusValue):
        raise ValueError("Invalid lorebook status.")


def _validate_lorebook_entry(
    command: Types.CreateLorebookEntryCommand | Types.UpdateLorebookEntryCommand,
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
        (command.entry_type, Types.LorebookEntryTypeValue, "entry type"),
        (
            command.activation_type,
            Types.LorebookEntryActivationTypeValue,
            "activation type",
        ),
        (command.match_mode, Types.LorebookEntryMatchModeValue, "match mode"),
        (command.placement, Types.LorebookEntryPlacementValue, "placement"),
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
                MatchingServiceUtil.validate_regex(trigger)
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
    session: AsyncSession, lorebook_id: UUID, owner_id: UUID
) -> Types.LorebookInfo:
    row = await Repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id, for_update=True
    )
    info = PersistenceMapper.lorebook_entity_to_info(row)
    if info is None:
        raise LookupError("Lorebook not found.")
    return info


async def create_lorebook(
    session: AsyncSession, command: Types.CreateLorebookCommand
) -> Types.LorebookInfo:
    async with use_case_transaction(session):
        _validate_lorebook_profile(command)
        _validate_lorebook_status(command.status)
        row = await Repository.create_lorebook_command(session, command)
        return PersistenceMapper.lorebook_entity_to_info(row)


async def update_lorebook(
    session: AsyncSession, command: Types.UpdateLorebookCommand
) -> Types.LorebookInfo:
    async with use_case_transaction(session):
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        _validate_lorebook_profile(command)
        row = await Repository.update_lorebook_command(session, command)
        return PersistenceMapper.lorebook_entity_to_info(row)


async def change_lorebook_status(
    session: AsyncSession, command: Types.ChangeLorebookStatusCommand
) -> Types.LorebookInfo:
    async with use_case_transaction(session):
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        _validate_lorebook_status(command.status)
        row = await Repository.change_lorebook_status_command(session, command)
        return PersistenceMapper.lorebook_entity_to_info(row)


async def delete_lorebook(
    session: AsyncSession, command: Types.DeleteLorebookCommand
) -> None:
    async with use_case_transaction(session):
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        await Repository.delete_lorebook_command(session, command)


async def create_lorebook_entry(
    session: AsyncSession, command: Types.CreateLorebookEntryCommand
) -> Types.LorebookEntryInfo:
    async with use_case_transaction(session):
        _validate_lorebook_entry(command)
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        row = await Repository.create_lorebook_entry_command(session, command)
        return PersistenceMapper.lorebook_entry_entity_to_info(row)


async def update_lorebook_entry(
    session: AsyncSession, command: Types.UpdateLorebookEntryCommand
) -> Types.LorebookEntryInfo:
    async with use_case_transaction(session):
        _validate_lorebook_entry(command)
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        row = await Repository.get_lorebook_entry(
            session, command.entry_id, command.lorebook_id, for_update=True
        )
        info = PersistenceMapper.lorebook_entry_entity_to_info(row)
        if info is None:
            raise LookupError("Lorebook entry not found.")
        row = await Repository.update_lorebook_entry_command(session, command)
        return PersistenceMapper.lorebook_entry_entity_to_info(row)


async def delete_lorebook_entry(
    session: AsyncSession, command: Types.DeleteLorebookEntryCommand
) -> None:
    async with use_case_transaction(session):
        await _get_owned_lorebook(session, command.lorebook_id, command.owner_id)
        row = await Repository.get_lorebook_entry(
            session, command.entry_id, command.lorebook_id, for_update=True
        )
        info = PersistenceMapper.lorebook_entry_entity_to_info(row)
        if info is None:
            raise LookupError("Lorebook entry not found.")
        await Repository.delete_lorebook_entry_command(session, command)


async def freeze_lorebook(
    session: AsyncSession, command: Types.FreezeLorebookCommand
) -> Types.LorebookSnapshotInfo:
    async with use_case_transaction(session):
        source = await _get_owned_lorebook(
            session, command.lorebook_id, command.owner_id
        )
        row = await Repository.freeze_lorebook(session, source)
        return PersistenceMapper.lorebook_snapshot_entity_to_info(row)
