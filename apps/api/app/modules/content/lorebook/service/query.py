# owner 조회와 인가가 끝난 ID용 내부 조회를 구분한다. 원본 활성화는 쿼리 우선순위, 스냅샷 활성화는 저장 순서를 따른다.
# 스냅샷 선택은 activation의 v1 옵션·수동 선택·예산 규칙을 사용한다. 원본 조회 활성화는 기존 규칙이다.
"""Lorebook reads and prompt-entry activation.

These functions never commit or roll back the caller's transaction. Management
reads return result dataclasses, and activation returns the smaller internal type
consumed by chat prompt assembly.
"""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.lorebook import repository as Repository
from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.mapper import persistence as PersistenceMapper
from app.modules.content.lorebook.service.activation import diagnose_entries
from app.modules.content.lorebook.service.util import matching as MatchingServiceUtil


def diagnose_draft_entries(
    command: Types.DiagnoseDraftEntriesCommand,
) -> tuple[list[Types.LorebookSnapshotEntryData], list[Types.LorebookEntryDiagnostic]]:
    """Validate transient entries using write rules, then use the snapshot selector.

    IDs here identify a transient draft only; this API cannot activate any live
    conversation or authorize arbitrary server lore. No database or AI is called.
    """
    from app.modules.content.lorebook.service.command import _validate_lorebook_entry

    if len(command.entries) > 100 or len(
        {str(entry["id"]) for entry in command.entries}
    ) != len(command.entries):
        raise ValueError("Draft lore IDs must be distinct and at most 100.")
    for entry in command.entries:
        # The command's typed entry fields match CreateLorebookEntryCommand;
        # removing only its transient ID preserves the original **kwargs behavior,
        # including rejection of unknown keys. Business validation still follows.
        entry_fields = cast(
            Types.LorebookEntryCommandFields,
            {key: field for key, field in entry.items() if key != "id"},
        )
        _validate_lorebook_entry(
            Types.CreateLorebookEntryCommand(
                lorebook_id=command.owner_id, owner_id=command.owner_id, **entry_fields
            )
        )
    return diagnose_entries(
        list(command.entries),
        messages=command.messages,
        manual_entry_ids=command.manual_entry_ids,
    )


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


# 인가된 고정 스냅샷에서 enabled 일반 항목의 always/keyword만 선택한다. DB 조회나 프롬프트 배치는 하지 않는다.
def activate_snapshot_entries(
    command: Types.ActivateSnapshotEntriesCommand,
) -> Types.ActivatedSnapshotEntriesInfo:
    """Select automatic entries from an authorized snapshot without reading live data.

    Legacy snapshots retain their order; opt-in v1 options control ranking,
    history search, budgets and exclusive groups. Manual IDs must belong to this
    snapshot. Semantic selection stays unsupported. Never mutate the snapshot.
    """
    active, _ = diagnose_entries(
        command.snapshot.snapshot_data["entries"],
        text=command.text,
        messages=command.messages,
        manual_entry_ids=command.manual_entry_ids,
    )
    return PersistenceMapper.lorebook_snapshot_entries_to_active_info(active)


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
    for entry_info in entries:
        triggers = entry_info.key_triggers or []
        if any(
            _keyword_matches(text, trigger, entry_info.match_mode)
            for trigger in triggers
        ):
            active.append(
                PersistenceMapper.lorebook_entry_info_to_active_info(entry_info)
            )
    return active


async def list_start_sets(
    session: AsyncSession, command: Types.ListStartSetsCommand
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


# 소유자에 속한 원본들을 조회하며 lock=True이면 정렬된 ID 순서로 잠근다. 누락이 있으면 LookupError다.
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
