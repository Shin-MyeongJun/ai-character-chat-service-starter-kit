# 항목 metadata는 얕은 dict 복사, 스냅샷 JSON과 활성 스냅샷 항목은 deepcopy다. 활성화 판단은 query가 수행한다.
from copy import deepcopy
from typing import cast, overload

from app.db.models import lorebook as lorebook_models
from app.modules.content.lorebook import repository as Repository
from app.modules.content.lorebook import types as Types


@overload
def lorebook_entity_to_info(entity: lorebook_models.Lorebook) -> Types.LorebookInfo: ...


@overload
def lorebook_entity_to_info(entity: None) -> None: ...


def lorebook_entity_to_info(
    entity: lorebook_models.Lorebook | None,
) -> Types.LorebookInfo | None:
    if entity is None:
        return None
    return Types.LorebookInfo(
        id=entity.id,
        owner_id=entity.owner_id,
        title=entity.title,
        description=entity.description,
        visibility=cast(Types.LorebookVisibilityValue, entity.visibility),
        status=cast(Types.LorebookStatusValue, entity.status),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@overload
def lorebook_entry_entity_to_info(
    entity: lorebook_models.LorebookEntry,
) -> Types.LorebookEntryInfo: ...


@overload
def lorebook_entry_entity_to_info(entity: None) -> None: ...


def lorebook_entry_entity_to_info(
    entity: lorebook_models.LorebookEntry | None,
) -> Types.LorebookEntryInfo | None:
    if entity is None:
        return None
    return Types.LorebookEntryInfo(
        id=entity.id,
        lorebook_id=entity.lorebook_id,
        title=entity.title,
        content=entity.content,
        entry_type=cast(Types.LorebookEntryTypeValue, entity.entry_type),
        activation_type=cast(
            Types.LorebookEntryActivationTypeValue, entity.activation_type
        ),
        key_triggers=list(entity.key_triggers)
        if entity.key_triggers is not None
        else None,
        match_mode=cast(Types.LorebookEntryMatchModeValue, entity.match_mode),
        priority=entity.priority,
        token_budget=entity.token_budget,
        placement=cast(Types.LorebookEntryPlacementValue, entity.placement),
        is_enabled=entity.is_enabled,
        metadata=dict(entity.metadata_ or {}),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def lorebook_entity_page_to_info(
    page: Repository.LorebookPageRow,
) -> Types.LorebookPage[Types.LorebookInfo]:
    return Types.LorebookPage(
        items=[lorebook_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def lorebook_entry_entity_page_to_info(
    page: Repository.LorebookEntryPageRow,
) -> Types.LorebookEntryPage[Types.LorebookEntryInfo]:
    return Types.LorebookEntryPage(
        items=[lorebook_entry_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@overload
def lorebook_entry_entity_to_active(
    entity: lorebook_models.LorebookEntry,
) -> Types.ActiveLorebookEntryInfo: ...


@overload
def lorebook_entry_entity_to_active(entity: None) -> None: ...


def lorebook_entry_entity_to_active(
    entity: lorebook_models.LorebookEntry | None,
) -> Types.ActiveLorebookEntryInfo | None:
    if entity is None:
        return None
    return Types.ActiveLorebookEntryInfo(
        entry_id=entity.id,
        lorebook_id=entity.lorebook_id,
        title=entity.title,
        content=entity.content,
        entry_type=cast(Types.LorebookEntryTypeValue, entity.entry_type),
        priority=entity.priority,
        token_budget=entity.token_budget,
        placement=cast(Types.LorebookEntryPlacementValue, entity.placement),
    )


def lorebook_entries_entities_to_info(entities) -> list[Types.LorebookEntryInfo]:
    return [lorebook_entry_entity_to_info(entity) for entity in entities]


def lorebook_entries_entities_to_active_info(
    entities,
) -> list[Types.ActiveLorebookEntryInfo]:
    return [lorebook_entry_entity_to_active(entity) for entity in entities]


def lorebook_entry_info_to_active_info(
    info: Types.LorebookEntryInfo,
) -> Types.ActiveLorebookEntryInfo:
    return Types.ActiveLorebookEntryInfo(
        entry_id=info.id,
        lorebook_id=info.lorebook_id,
        title=info.title,
        content=info.content,
        entry_type=info.entry_type,
        priority=info.priority,
        token_budget=info.token_budget,
        placement=info.placement,
    )


def lorebooks_entities_to_info(entities) -> list[Types.LorebookInfo]:
    return [lorebook_entity_to_info(entity) for entity in entities]


def lorebook_snapshot_entity_to_info(entity) -> Types.LorebookSnapshotInfo:
    return Types.LorebookSnapshotInfo(
        entity.id, entity.lorebook_id, entity.version, deepcopy(entity.snapshot_data)
    )


def lorebook_snapshots_entities_to_info(entities) -> list[Types.LorebookSnapshotInfo]:
    return [lorebook_snapshot_entity_to_info(entity) for entity in entities]


def lorebook_snapshot_entries_to_active_info(
    entries: list[dict],
) -> Types.ActivatedSnapshotEntriesInfo:
    return Types.ActivatedSnapshotEntriesInfo(entries=deepcopy(entries))
