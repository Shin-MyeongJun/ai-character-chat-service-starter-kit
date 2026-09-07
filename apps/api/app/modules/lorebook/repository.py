from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.lorebook import Lorebook, LorebookEntry
from app.modules.lorebook.types import (
    LorebookCursor,
    LorebookEntryPage,
    LorebookPage,
)

DEFAULT_LOREBOOK_LIST_LIMIT = 50
MAX_LOREBOOK_LIST_LIMIT = 100


def _normalize_list_limit(limit: int) -> int:
    return min(max(limit, 1), MAX_LOREBOOK_LIST_LIMIT)


def _apply_lorebook_cursor(
    stmt: Select[tuple[Lorebook]],
    cursor: LorebookCursor | None,
) -> Select[tuple[Lorebook]]:
    if cursor is None:
        return stmt
    return stmt.where(
        or_(
            Lorebook.created_at < cursor.created_at,
            and_(
                Lorebook.created_at == cursor.created_at,
                Lorebook.id < cursor.id,
            ),
        )
    )


def _apply_entry_cursor(
    stmt: Select[tuple[LorebookEntry]],
    cursor: LorebookCursor | None,
) -> Select[tuple[LorebookEntry]]:
    if cursor is None:
        return stmt
    return stmt.where(
        or_(
            LorebookEntry.created_at < cursor.created_at,
            and_(
                LorebookEntry.created_at == cursor.created_at,
                LorebookEntry.id < cursor.id,
            ),
        )
    )


def _build_lorebook_page(
    items: list[Lorebook],
    limit: int,
) -> LorebookPage[Lorebook]:
    page_items = items[:limit]
    next_cursor = None
    if len(items) > limit and page_items:
        last = page_items[-1]
        next_cursor = LorebookCursor(created_at=last.created_at, id=last.id)
    return LorebookPage(items=page_items, next_cursor=next_cursor)


def _build_entry_page(
    items: list[LorebookEntry],
    limit: int,
) -> LorebookEntryPage[LorebookEntry]:
    page_items = items[:limit]
    next_cursor = None
    if len(items) > limit and page_items:
        last = page_items[-1]
        next_cursor = LorebookCursor(created_at=last.created_at, id=last.id)
    return LorebookEntryPage(items=page_items, next_cursor=next_cursor)


async def _fetch_lorebook_page(
    session: AsyncSession,
    stmt: Select[tuple[Lorebook]],
    *,
    cursor: LorebookCursor | None,
    limit: int,
) -> LorebookPage[Lorebook]:
    normalized_limit = _normalize_list_limit(limit)
    stmt = (
        _apply_lorebook_cursor(stmt, cursor)
        .order_by(Lorebook.created_at.desc(), Lorebook.id.desc())
        .limit(normalized_limit + 1)
    )
    result = await session.scalars(stmt)
    return _build_lorebook_page(list(result.all()), normalized_limit)


async def _fetch_entry_page(
    session: AsyncSession,
    stmt: Select[tuple[LorebookEntry]],
    *,
    cursor: LorebookCursor | None,
    limit: int,
) -> LorebookEntryPage[LorebookEntry]:
    normalized_limit = _normalize_list_limit(limit)
    stmt = (
        _apply_entry_cursor(stmt, cursor)
        .order_by(LorebookEntry.created_at.desc(), LorebookEntry.id.desc())
        .limit(normalized_limit + 1)
    )
    result = await session.scalars(stmt)
    return _build_entry_page(list(result.all()), normalized_limit)


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
) -> LorebookPage[Lorebook]:
    return await _fetch_lorebook_page(
        session, select(Lorebook), cursor=cursor, limit=limit
    )


async def list_lorebooks_by_owner_id(
    session: AsyncSession,
    owner_id: UUID,
    cursor: LorebookCursor | None = None,
    limit: int = DEFAULT_LOREBOOK_LIST_LIMIT,
) -> LorebookPage[Lorebook]:
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
) -> LorebookEntryPage[LorebookEntry]:
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
