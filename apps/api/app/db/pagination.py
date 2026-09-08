"""Descending (created_at, id) cursor pagination for scoped entity queries."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


class CursorItem(Protocol):
    @property
    def created_at(self) -> datetime: ...

    @property
    def id(self) -> UUID: ...


TItem = TypeVar("TItem", bound=CursorItem)
TCursor = TypeVar("TCursor", bound=CursorItem)
TPage = TypeVar("TPage")


async def fetch_cursor_page(
    session: AsyncSession,
    stmt: Select[tuple[TItem]],
    *,
    created_at: InstrumentedAttribute[datetime],
    id_column: InstrumentedAttribute[UUID],
    cursor: TCursor | None,
    limit: int,
    max_limit: int,
    cursor_factory: Callable[[datetime, UUID], TCursor],
    page_factory: Callable[[list[TItem], TCursor | None], TPage],
) -> TPage:
    """Keep caller filters and fetch one extra row to detect the next page."""
    limit = min(max(limit, 1), max_limit)
    if cursor is not None:
        stmt = stmt.where(
            or_(
                created_at < cursor.created_at,
                and_(created_at == cursor.created_at, id_column < cursor.id),
            )
        )
    stmt = stmt.order_by(created_at.desc(), id_column.desc()).limit(limit + 1)
    rows = list((await session.scalars(stmt)).all())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit and items:
        last = items[-1]
        next_cursor = cursor_factory(last.created_at, last.id)
    return page_factory(items, next_cursor)
