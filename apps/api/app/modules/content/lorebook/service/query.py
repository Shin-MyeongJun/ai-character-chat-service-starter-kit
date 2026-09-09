"""Lorebook reads and prompt-entry activation.

These functions never commit or roll back the caller's transaction. Management
reads return result dataclasses, and activation returns the smaller internal type
consumed by chat prompt assembly.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.lorebook import matching, repository, types
from app.modules.content.lorebook.mapper import persistence


async def list_lorebooks(
    session: AsyncSession,
    *,
    cursor: types.LorebookCursor | None = None,
    limit: int = repository.DEFAULT_LOREBOOK_LIST_LIMIT,
) -> types.LorebookPage[types.LorebookInfo]:
    page = await repository.list_lorebooks(session, cursor=cursor, limit=limit)
    return persistence.lorebook_entity_page_to_info(page)


async def list_lorebooks_by_owner_id(
    session: AsyncSession,
    *,
    owner_id: UUID,
    cursor: types.LorebookCursor | None = None,
    limit: int = repository.DEFAULT_LOREBOOK_LIST_LIMIT,
) -> types.LorebookPage[types.LorebookInfo]:
    page = await repository.list_lorebooks_by_owner_id(
        session,
        owner_id,
        cursor=cursor,
        limit=limit,
    )
    return persistence.lorebook_entity_page_to_info(page)


async def get_lorebook_by_id(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
) -> types.LorebookInfo | None:
    entity = await repository.get_lorebook_by_id(session, lorebook_id)
    if entity is None:
        return None
    return persistence.lorebook_entity_to_info(entity)


async def get_lorebook_by_id_and_owner_id(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
    owner_id: UUID,
) -> types.LorebookInfo | None:
    entity = await repository.get_lorebook_by_id_and_owner_id(
        session,
        lorebook_id,
        owner_id,
    )
    if entity is None:
        return None
    return persistence.lorebook_entity_to_info(entity)


async def list_lorebook_entries(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
    cursor: types.LorebookCursor | None = None,
    limit: int = repository.DEFAULT_LOREBOOK_LIST_LIMIT,
) -> types.LorebookEntryPage[types.LorebookEntryInfo]:
    page = await repository.list_lorebook_entries(
        session,
        lorebook_id,
        cursor=cursor,
        limit=limit,
    )
    return persistence.lorebook_entry_entity_page_to_info(page)


async def list_lorebook_entries_by_owner_id(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
    owner_id: UUID,
    cursor: types.LorebookCursor | None = None,
    limit: int = repository.DEFAULT_LOREBOOK_LIST_LIMIT,
) -> types.LorebookEntryPage[types.LorebookEntryInfo] | None:
    parent = await repository.get_lorebook_by_id_and_owner_id(
        session,
        lorebook_id,
        owner_id,
    )
    if parent is None:
        return None
    return await list_lorebook_entries(
        session,
        lorebook_id=lorebook_id,
        cursor=cursor,
        limit=limit,
    )


async def get_lorebook_entry(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
    entry_id: UUID,
) -> types.LorebookEntryInfo | None:
    entity = await repository.get_lorebook_entry(
        session,
        entry_id,
        lorebook_id,
    )
    if entity is None:
        return None
    return persistence.lorebook_entry_entity_to_info(entity)


async def get_lorebook_entry_by_owner_id(
    session: AsyncSession,
    *,
    lorebook_id: UUID,
    entry_id: UUID,
    owner_id: UUID,
) -> types.LorebookEntryInfo | None:
    parent = await repository.get_lorebook_by_id_and_owner_id(
        session,
        lorebook_id,
        owner_id,
    )
    if parent is None:
        return None
    return await get_lorebook_entry(
        session,
        lorebook_id=lorebook_id,
        entry_id=entry_id,
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
            return matching.regex_matches(trigger, text)
        except matching.InvalidLorebookRegex as exc:
            raise ValueError(
                "Stored lorebook entry has an invalid regular expression."
            ) from exc
    raise ValueError("Stored lorebook entry has an invalid match mode.")


async def get_always_entries(
    session: AsyncSession,
    *,
    lorebook_ids: Sequence[UUID],
) -> list[types.ActiveLorebookEntry]:
    """Return enabled always-on entries for already-authorized lorebooks."""
    entities = await repository.list_enabled_entries_by_activation_type(
        session,
        _unique_lorebook_ids(lorebook_ids),
        "always",
    )
    return [persistence.lorebook_entry_entity_to_active(item) for item in entities]


async def activate_keyword_entries(
    session: AsyncSession,
    *,
    lorebook_ids: Sequence[UUID],
    text: str,
) -> list[types.ActiveLorebookEntry]:
    """Match enabled keyword entries for already-authorized lorebooks."""
    if not text:
        return []
    entities = await repository.list_enabled_entries_by_activation_type(
        session,
        _unique_lorebook_ids(lorebook_ids),
        "keyword",
    )
    active = []
    for entity in entities:
        triggers = entity.key_triggers or []
        if any(
            _keyword_matches(text, trigger, entity.match_mode) for trigger in triggers
        ):
            active.append(persistence.lorebook_entry_entity_to_active(entity))
    return active


async def list_start_sets(session, *, lorebook_id, owner_id):
    parent = await repository.get_lorebook_by_id_and_owner_id(
        session, lorebook_id, owner_id
    )
    if parent is None:
        raise LookupError("Lorebook not found.")
    return [
        persistence.lorebook_entry_entity_to_info(e)
        for e in await repository.list_start_sets(session, lorebook_id)
    ]
