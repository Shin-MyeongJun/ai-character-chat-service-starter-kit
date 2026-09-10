from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import lorebook as lorebook_models
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.db.models.snapshot.lorebook import LorebookSnapshot
from app.db.pagination import fetch_cursor_page
from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.types import (
    LorebookCursor,
)

DEFAULT_LOREBOOK_LIST_LIMIT = 50
MAX_LOREBOOK_LIST_LIMIT = 100


@dataclass(frozen=True)
class LorebookPageRow:
    items: list[Lorebook]
    next_cursor: Types.LorebookCursor | None


@dataclass(frozen=True)
class LorebookEntryPageRow:
    items: list[LorebookEntry]
    next_cursor: Types.LorebookCursor | None


async def _fetch_lorebook_page(
    session: AsyncSession,
    stmt: Select[tuple[Lorebook]],
    *,
    cursor: LorebookCursor | None,
    limit: int,
) -> LorebookPageRow:
    return await fetch_cursor_page(
        session,
        stmt,
        created_at=Lorebook.created_at,
        id_column=Lorebook.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_LOREBOOK_LIST_LIMIT,
        cursor_factory=LorebookCursor,
        page_factory=LorebookPageRow,
    )


async def _fetch_entry_page(
    session: AsyncSession,
    stmt: Select[tuple[LorebookEntry]],
    *,
    cursor: LorebookCursor | None,
    limit: int,
) -> LorebookEntryPageRow:
    return await fetch_cursor_page(
        session,
        stmt,
        created_at=LorebookEntry.created_at,
        id_column=LorebookEntry.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_LOREBOOK_LIST_LIMIT,
        cursor_factory=LorebookCursor,
        page_factory=LorebookEntryPageRow,
    )


async def create_lorebook(
    session: AsyncSession,
    lorebook: Lorebook,
) -> Lorebook:
    session.add(lorebook)
    await session.flush()
    await session.refresh(lorebook)
    return lorebook


async def get_lorebook_by_id(
    session: AsyncSession,
    lorebook_id: UUID,
) -> Lorebook | None:
    result = await session.scalars(select(Lorebook).where(Lorebook.id == lorebook_id))
    return result.one_or_none()


async def get_lorebook_by_id_and_owner_id(
    session: AsyncSession,
    lorebook_id: UUID,
    owner_id: UUID,
    *,
    for_update: bool = False,
) -> Lorebook | None:
    stmt = select(Lorebook).where(
        Lorebook.id == lorebook_id,
        Lorebook.owner_id == owner_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.scalars(stmt)
    return result.one_or_none()


async def list_lorebooks(
    session: AsyncSession,
    cursor: LorebookCursor | None = None,
    limit: int = DEFAULT_LOREBOOK_LIST_LIMIT,
) -> LorebookPageRow:
    return await _fetch_lorebook_page(
        session, select(Lorebook), cursor=cursor, limit=limit
    )


async def list_lorebooks_by_owner_id(
    session: AsyncSession,
    owner_id: UUID,
    cursor: LorebookCursor | None = None,
    limit: int = DEFAULT_LOREBOOK_LIST_LIMIT,
) -> LorebookPageRow:
    stmt = select(Lorebook).where(Lorebook.owner_id == owner_id)
    return await _fetch_lorebook_page(session, stmt, cursor=cursor, limit=limit)


async def update_lorebook(
    session: AsyncSession,
    lorebook: Lorebook,
) -> Lorebook:
    session.add(lorebook)
    await session.flush()
    await session.refresh(lorebook)
    return lorebook


async def delete_lorebook(session: AsyncSession, lorebook: Lorebook) -> None:
    await session.delete(lorebook)
    await session.flush()


async def create_lorebook_entry(
    session: AsyncSession,
    entry: LorebookEntry,
) -> LorebookEntry:
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


async def get_lorebook_entry(
    session: AsyncSession,
    entry_id: UUID,
    lorebook_id: UUID,
    *,
    for_update: bool = False,
) -> LorebookEntry | None:
    stmt = select(LorebookEntry).where(
        LorebookEntry.id == entry_id,
        LorebookEntry.lorebook_id == lorebook_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.scalars(stmt)
    return result.one_or_none()


async def list_lorebook_entries(
    session: AsyncSession,
    lorebook_id: UUID,
    cursor: LorebookCursor | None = None,
    limit: int = DEFAULT_LOREBOOK_LIST_LIMIT,
) -> LorebookEntryPageRow:
    stmt = select(LorebookEntry).where(LorebookEntry.lorebook_id == lorebook_id)
    return await _fetch_entry_page(session, stmt, cursor=cursor, limit=limit)


async def list_enabled_entries_by_activation_type(
    session: AsyncSession,
    lorebook_ids: Sequence[UUID],
    activation_type: str,
) -> list[LorebookEntry]:
    if not lorebook_ids:
        return []
    stmt = (
        select(LorebookEntry)
        .where(
            LorebookEntry.lorebook_id.in_(lorebook_ids),
            LorebookEntry.is_enabled.is_(True),
            LorebookEntry.activation_type == activation_type,
            LorebookEntry.entry_type != "start_set",
        )
        .order_by(
            LorebookEntry.priority.desc(),
            LorebookEntry.created_at.asc(),
            LorebookEntry.id.asc(),
        )
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def update_lorebook_entry(
    session: AsyncSession,
    entry: LorebookEntry,
) -> LorebookEntry:
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


async def delete_lorebook_entry(
    session: AsyncSession,
    entry: LorebookEntry,
) -> None:
    await session.delete(entry)
    await session.flush()


async def list_start_sets(
    session: AsyncSession, lorebook_id: UUID
) -> list[LorebookEntry]:
    return list(
        await session.scalars(
            select(LorebookEntry)
            .where(
                LorebookEntry.lorebook_id == lorebook_id,
                LorebookEntry.entry_type == "start_set",
                LorebookEntry.is_enabled.is_(True),
            )
            .order_by(LorebookEntry.priority.desc(), LorebookEntry.id)
        )
    )


def _create_lorebook_entity(
    command: Types.CreateLorebookCommand,
) -> lorebook_models.Lorebook:
    return lorebook_models.Lorebook(
        owner_id=command.owner_id,
        title=command.title,
        description=command.description,
        visibility=command.visibility,
        status=command.status,
    )


def _apply_lorebook_update(
    entity: lorebook_models.Lorebook,
    command: Types.UpdateLorebookCommand,
) -> lorebook_models.Lorebook:
    entity.title = command.title
    entity.description = command.description
    entity.visibility = command.visibility
    return entity


def _apply_lorebook_status_change(
    entity: lorebook_models.Lorebook,
    command: Types.ChangeLorebookStatusCommand,
) -> lorebook_models.Lorebook:
    entity.status = command.status
    return entity


def _create_lorebook_entry_entity(
    command: Types.CreateLorebookEntryCommand,
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


def _apply_lorebook_entry_update(
    entity: lorebook_models.LorebookEntry,
    command: Types.UpdateLorebookEntryCommand,
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


async def create_lorebook_command(
    session: AsyncSession, command: Types.CreateLorebookCommand
):
    entity = _create_lorebook_entity(command)
    return await create_lorebook(session, entity)


async def update_lorebook_command(
    session: AsyncSession, command: Types.UpdateLorebookCommand
):
    entity = await get_lorebook_by_id_and_owner_id(
        session, command.lorebook_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_lorebook_update(entity, command)
    return await update_lorebook(session, entity)


async def change_lorebook_status_command(
    session: AsyncSession, command: Types.ChangeLorebookStatusCommand
):
    entity = await get_lorebook_by_id_and_owner_id(
        session, command.lorebook_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_lorebook_status_change(entity, command)
    return await update_lorebook(session, entity)


async def delete_lorebook_command(
    session: AsyncSession, command: Types.DeleteLorebookCommand
):
    entity = await get_lorebook_by_id_and_owner_id(
        session, command.lorebook_id, command.owner_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    await delete_lorebook(session, entity)


async def create_lorebook_entry_command(
    session: AsyncSession, command: Types.CreateLorebookEntryCommand
):
    entity = _create_lorebook_entry_entity(command)
    return await create_lorebook_entry(session, entity)


async def update_lorebook_entry_command(
    session: AsyncSession, command: Types.UpdateLorebookEntryCommand
):
    entity = await get_lorebook_entry(
        session, command.entry_id, command.lorebook_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    entity = _apply_lorebook_entry_update(entity, command)
    return await update_lorebook_entry(session, entity)


async def delete_lorebook_entry_command(
    session: AsyncSession, command: Types.DeleteLorebookEntryCommand
):
    entity = await get_lorebook_entry(
        session, command.entry_id, command.lorebook_id, for_update=True
    )
    assert entity is not None, "Previously locked record disappeared."
    await delete_lorebook_entry(session, entity)


async def list_owned_lorebooks(
    session: AsyncSession, ids: tuple[UUID, ...], owner_id: UUID, *, lock=False
):
    stmt = (
        select(Lorebook)
        .where(Lorebook.id.in_(ids), Lorebook.owner_id == owner_id)
        .order_by(Lorebook.id)
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list(await session.scalars(stmt))


async def list_start_entries(session, ids, lorebook_ids=None):
    stmt = select(LorebookEntry).where(
        LorebookEntry.id.in_(ids),
        LorebookEntry.entry_type == "start_set",
        LorebookEntry.is_enabled.is_(True),
    )
    if lorebook_ids is not None:
        stmt = stmt.where(LorebookEntry.lorebook_id.in_(lorebook_ids))
    return list(await session.scalars(stmt))


async def next_version(session, cls, column, source_id):
    return (
        await session.scalar(select(func.max(cls.version)).where(column == source_id))
        or 0
    ) + 1


async def freeze_lorebook(session, source):
    entries = []
    for entry in await session.scalars(
        select(LorebookEntry)
        .where(LorebookEntry.lorebook_id == source.id)
        .order_by(LorebookEntry.id)
    ):
        item = {
            key: getattr(entry, key)
            for key in (
                "title",
                "content",
                "entry_type",
                "activation_type",
                "key_triggers",
                "match_mode",
                "priority",
                "token_budget",
                "placement",
                "is_enabled",
            )
        }
        item.update(id=str(entry.id), metadata=entry.metadata_)
        entries.append(item)
    snapshot = LorebookSnapshot(
        id=uuid4(),
        lorebook_id=source.id,
        version=await next_version(
            session, LorebookSnapshot, LorebookSnapshot.lorebook_id, source.id
        ),
        snapshot_schema_version=2,
        snapshot_data={
            "title": source.title,
            "description": source.description,
            "entries": entries,
        },
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def list_lorebook_snapshots(session, snapshot_ids):
    return list(
        await session.scalars(
            select(LorebookSnapshot).where(LorebookSnapshot.id.in_(snapshot_ids))
        )
    )
