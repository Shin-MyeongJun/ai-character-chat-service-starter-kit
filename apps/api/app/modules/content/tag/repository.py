"""Dictionary persistence only; content connections belong to their modules."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tag import Tag


async def get_tag(
    session: AsyncSession, tag_id: UUID, *, exclusive: bool = False
) -> Tag | None:
    stmt = select(Tag).where(Tag.id == tag_id)
    stmt = stmt.with_for_update() if exclusive else stmt
    return (
        await session.scalars(stmt.execution_options(populate_existing=True))
    ).first()


async def get_tag_by_name(session: AsyncSession, name: str) -> Tag | None:
    return (await session.scalars(select(Tag).where(Tag.name == name))).first()


async def get_tags(session: AsyncSession, tag_ids: Sequence[UUID]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(await session.scalars(select(Tag).where(Tag.id.in_(tag_ids))))


async def resolve_tag(
    session: AsyncSession, name: str, description: str | None = None
) -> Tag | None:
    # ON CONFLICT waits for concurrent inserts without poisoning the transaction.
    await session.execute(
        insert(Tag)
        .values(name=name, description=description)
        .on_conflict_do_nothing(index_elements=[Tag.name])
    )
    # Hold activity/name stable until the caller finishes writing its connections.
    return (
        await session.scalars(
            select(Tag)
            .where(Tag.name == name)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    ).first()


async def update_tag(
    session: AsyncSession, tag_id: UUID, name: str, description: str | None
) -> Tag | None:
    return (
        await session.scalars(
            update(Tag)
            .where(Tag.id == tag_id)
            .values(name=name, description=description)
            .returning(Tag)
            .execution_options(populate_existing=True)
        )
    ).first()


async def deactivate_tag(session: AsyncSession, tag_id: UUID) -> Tag | None:
    return (
        await session.scalars(
            update(Tag)
            .where(Tag.id == tag_id)
            .values(is_active=False)
            .returning(Tag)
            .execution_options(populate_existing=True)
        )
    ).first()
