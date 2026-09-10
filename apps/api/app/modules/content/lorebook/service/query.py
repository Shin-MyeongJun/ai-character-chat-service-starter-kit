"""Lorebook reads and prompt-entry activation.

These functions never commit or roll back the caller's transaction. Management
reads return result dataclasses, and activation returns the smaller internal type
consumed by chat prompt assembly.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.lorebook import repository as Repository
from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.mapper import persistence as PersistenceMapper
from app.modules.content.lorebook.service.util import matching as MatchingServiceUtil


async def list_lorebooks(
    session: AsyncSession, command: Types.ListLorebooksCommand
) -> Types.LorebookPage[Types.LorebookInfo]:
    cursor = command.cursor
    limit = command.limit
    page = await Repository.list_lorebooks(session, cursor=cursor, limit=limit)
    return PersistenceMapper.lorebook_entity_page_to_info(page)


async def list_lorebooks_by_owner_id(
    session: AsyncSession, command: Types.ListLorebooksByOwnerIdCommand
) -> Types.LorebookPage[Types.LorebookInfo]:
    owner_id = command.owner_id
    cursor = command.cursor
    limit = command.limit
    page = await Repository.list_lorebooks_by_owner_id(
        session, owner_id, cursor=cursor, limit=limit
    )
    return PersistenceMapper.lorebook_entity_page_to_info(page)


async def get_lorebook_by_id(
    session: AsyncSession, command: Types.GetLorebookByIdCommand
) -> Types.LorebookInfo | None:
    lorebook_id = command.lorebook_id
    entity = await Repository.get_lorebook_by_id(session, lorebook_id)
    return PersistenceMapper.lorebook_entity_to_info(entity)


async def get_lorebook_by_id_and_owner_id(
    session: AsyncSession, command: Types.GetLorebookByIdAndOwnerIdCommand
) -> Types.LorebookInfo | None:
    lorebook_id = command.lorebook_id
    owner_id = command.owner_id
    entity = await Repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id
    )
    return PersistenceMapper.lorebook_entity_to_info(entity)


async def list_lorebook_entries(
    session: AsyncSession, command: Types.ListLorebookEntriesCommand
) -> Types.LorebookEntryPage[Types.LorebookEntryInfo]:
    lorebook_id = command.lorebook_id
    cursor = command.cursor
    limit = command.limit
    page = await Repository.list_lorebook_entries(
        session, lorebook_id, cursor=cursor, limit=limit
    )
    return PersistenceMapper.lorebook_entry_entity_page_to_info(page)


async def list_lorebook_entries_by_owner_id(
    session: AsyncSession, command: Types.ListLorebookEntriesByOwnerIdCommand
) -> Types.LorebookEntryPage[Types.LorebookEntryInfo] | None:
    lorebook_id = command.lorebook_id
    owner_id = command.owner_id
    cursor = command.cursor
    limit = command.limit
    parent = await Repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id
    )
    parent_info = PersistenceMapper.lorebook_entity_to_info(parent)
    if parent_info is None:
        return None
    return await list_lorebook_entries(
        session,
        Types.ListLorebookEntriesCommand(
            lorebook_id=lorebook_id, cursor=cursor, limit=limit
        ),
    )


async def get_lorebook_entry(
    session: AsyncSession, command: Types.GetLorebookEntryCommand
) -> Types.LorebookEntryInfo | None:
    lorebook_id = command.lorebook_id
    entry_id = command.entry_id
    entity = await Repository.get_lorebook_entry(session, entry_id, lorebook_id)
    return PersistenceMapper.lorebook_entry_entity_to_info(entity)


async def get_lorebook_entry_by_owner_id(
    session: AsyncSession, command: Types.GetLorebookEntryByOwnerIdCommand
) -> Types.LorebookEntryInfo | None:
    lorebook_id = command.lorebook_id
    entry_id = command.entry_id
    owner_id = command.owner_id
    parent = await Repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id
    )
    parent_info = PersistenceMapper.lorebook_entity_to_info(parent)
    if parent_info is None:
        return None
    return await get_lorebook_entry(
        session,
        Types.GetLorebookEntryCommand(lorebook_id=lorebook_id, entry_id=entry_id),
    )


def _unique_lorebook_ids(lorebook_ids: Sequence[UUID]) -> list[UUID]:
    return list(dict.fromkeys(lorebook_ids))


def _keyword_matches(text: str, trigger: str, match_mode: str) -> bool:
    if match_mode == "exact":
        return text.casefold() == trigger.casefold()
    if match_mode == "contains":
        return trigger.casefold() in text.casefold()
    if match_mode == "regex":
        try:
            return MatchingServiceUtil.regex_matches(trigger, text)
        except MatchingServiceUtil.InvalidLorebookRegex as exc:
            raise ValueError(
                "Stored lorebook entry has an invalid regular expression."
            ) from exc
    raise ValueError("Stored lorebook entry has an invalid match mode.")


async def get_always_entries(
    session: AsyncSession, command: Types.GetAlwaysEntriesCommand
) -> list[Types.ActiveLorebookEntryInfo]:
    """Return enabled always-on entries for already-authorized lorebooks."""
    lorebook_ids = command.lorebook_ids
    entities = await Repository.list_enabled_entries_by_activation_type(
        session, _unique_lorebook_ids(lorebook_ids), "always"
    )
    return PersistenceMapper.lorebook_entries_entities_to_active_info(entities)


async def activate_keyword_entries(
    session: AsyncSession, command: Types.ActivateKeywordEntriesCommand
) -> list[Types.ActiveLorebookEntryInfo]:
    """Match enabled keyword entries for already-authorized lorebooks."""
    lorebook_ids = command.lorebook_ids
    text = command.text
    if not text:
        return []
    entities = await Repository.list_enabled_entries_by_activation_type(
        session, _unique_lorebook_ids(lorebook_ids), "keyword"
    )
    entries = PersistenceMapper.lorebook_entries_entities_to_info(entities)
    active = []
    for entity in entries:
        triggers = entity.key_triggers or []
        if any(
            _keyword_matches(text, trigger, entity.match_mode) for trigger in triggers
        ):
            active.append(PersistenceMapper.lorebook_entry_info_to_active_info(entity))
    return active


async def list_start_sets(
    session, command: Types.ListStartSetsCommand
) -> list[Types.LorebookEntryInfo]:
    lorebook_id = command.lorebook_id
    owner_id = command.owner_id
    parent = await Repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id
    )
    parent_info = PersistenceMapper.lorebook_entity_to_info(parent)
    if parent_info is None:
        raise LookupError("Lorebook not found.")
    rows = await Repository.list_start_sets(session, lorebook_id)
    return PersistenceMapper.lorebook_entries_entities_to_info(rows)


async def get_owned_lorebooks(
    session: AsyncSession, command: Types.GetOwnedLorebooksCommand
) -> list[Types.LorebookInfo]:
    rows = await Repository.list_owned_lorebooks(
        session, command.ids, command.owner_id, lock=command.lock
    )
    infos = PersistenceMapper.lorebooks_entities_to_info(rows)
    if len(infos) != len(command.ids):
        raise LookupError("Owned component not found.")
    return infos


async def get_start_entries(
    session: AsyncSession, command: Types.GetStartEntriesCommand
) -> list[Types.LorebookEntryInfo]:
    rows = await Repository.list_start_entries(
        session, command.ids, command.lorebook_ids
    )
    return PersistenceMapper.lorebook_entries_entities_to_info(rows)


async def get_lorebook_snapshots(
    session: AsyncSession, command: Types.GetLorebookSnapshotsCommand
) -> list[Types.LorebookSnapshotInfo]:
    rows = await Repository.list_lorebook_snapshots(session, command.snapshot_ids)
    return PersistenceMapper.lorebook_snapshots_entities_to_info(rows)
