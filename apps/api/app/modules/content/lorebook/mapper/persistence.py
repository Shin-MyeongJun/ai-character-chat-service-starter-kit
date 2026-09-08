from typing import cast

from app.db.models import lorebook as lorebook_models
from app.modules.content.lorebook import types


def lorebook_create_to_entity(
    command: types.LorebookCreate,
) -> lorebook_models.Lorebook:
    return lorebook_models.Lorebook(
        owner_id=command.owner_id,
        title=command.title,
        description=command.description,
        visibility=command.visibility,
        status=command.status,
    )


def apply_lorebook_update_to_entity(
    entity: lorebook_models.Lorebook,
    command: types.LorebookUpdate,
) -> lorebook_models.Lorebook:
    entity.title = command.title
    entity.description = command.description
    entity.visibility = command.visibility
    return entity


def apply_lorebook_status_change_to_entity(
    entity: lorebook_models.Lorebook,
    command: types.LorebookStatusChange,
) -> lorebook_models.Lorebook:
    entity.status = command.status
    return entity


def lorebook_entry_create_to_entity(
    command: types.LorebookEntryCreate,
) -> lorebook_models.LorebookEntry:
    return lorebook_models.LorebookEntry(
        lorebook_id=command.lorebook_id,
        title=command.title,
        content=command.content,
        entry_type=command.entry_type,
        activation_type=command.activation_type,
        key_triggers=(
            list(command.key_triggers) if command.key_triggers is not None else None
        ),
        match_mode=command.match_mode,
        priority=command.priority,
        token_budget=command.token_budget,
        placement=command.placement,
        is_enabled=command.is_enabled,
        metadata_=dict(command.metadata or {}),
    )


def apply_lorebook_entry_update_to_entity(
    entity: lorebook_models.LorebookEntry,
    command: types.LorebookEntryUpdate,
) -> lorebook_models.LorebookEntry:
    entity.title = command.title
    entity.content = command.content
    entity.entry_type = command.entry_type
    entity.activation_type = command.activation_type
    entity.key_triggers = (
        list(command.key_triggers) if command.key_triggers is not None else None
    )
    entity.match_mode = command.match_mode
    entity.priority = command.priority
    entity.token_budget = command.token_budget
    entity.placement = command.placement
    entity.is_enabled = command.is_enabled
    entity.metadata_ = dict(command.metadata or {})
    return entity


def lorebook_entity_to_info(
    entity: lorebook_models.Lorebook,
) -> types.LorebookInfo:
    return types.LorebookInfo(
        id=entity.id,
        owner_id=entity.owner_id,
        title=entity.title,
        description=entity.description,
        visibility=cast(types.LorebookVisibilityValue, entity.visibility),
        status=cast(types.LorebookStatusValue, entity.status),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def lorebook_entry_entity_to_info(
    entity: lorebook_models.LorebookEntry,
) -> types.LorebookEntryInfo:
    return types.LorebookEntryInfo(
        id=entity.id,
        lorebook_id=entity.lorebook_id,
        title=entity.title,
        content=entity.content,
        entry_type=cast(types.LorebookEntryTypeValue, entity.entry_type),
        activation_type=cast(
            types.LorebookEntryActivationTypeValue, entity.activation_type
        ),
        key_triggers=(
            list(entity.key_triggers) if entity.key_triggers is not None else None
        ),
        match_mode=cast(types.LorebookEntryMatchModeValue, entity.match_mode),
        priority=entity.priority,
        token_budget=entity.token_budget,
        placement=cast(types.LorebookEntryPlacementValue, entity.placement),
        is_enabled=entity.is_enabled,
        metadata=dict(entity.metadata_ or {}),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def lorebook_entity_page_to_info(
    page: types.LorebookPage[lorebook_models.Lorebook],
) -> types.LorebookPage[types.LorebookInfo]:
    return types.LorebookPage(
        items=[lorebook_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def lorebook_entry_entity_page_to_info(
    page: types.LorebookEntryPage[lorebook_models.LorebookEntry],
) -> types.LorebookEntryPage[types.LorebookEntryInfo]:
    return types.LorebookEntryPage(
        items=[lorebook_entry_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def lorebook_entry_entity_to_active(
    entity: lorebook_models.LorebookEntry,
) -> types.ActiveLorebookEntry:
    return types.ActiveLorebookEntry(
        entry_id=entity.id,
        lorebook_id=entity.lorebook_id,
        title=entity.title,
        content=entity.content,
        entry_type=cast(types.LorebookEntryTypeValue, entity.entry_type),
        priority=entity.priority,
        token_budget=entity.token_budget,
        placement=cast(types.LorebookEntryPlacementValue, entity.placement),
    )
