"""Dictionary persistence only; content connections belong to their modules."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import case, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.tag import Tag

_RESOLVE_BATCH_SIZE = 500


async def lock_dictionary_for_update(session: AsyncSession) -> None:
    # Resolvers retain ROW EXCLUSIVE (INSERT) and ROW SHARE (FOR SHARE)
    # through the outer transaction, across every batch. EXCLUSIVE fences both
    # before any admin row/UNIQUE wait. NOWAIT is essential: the caller may
    # already hold rows needed by a resolver, so waiting here could deadlock.
    # Ordinary SELECT remains compatible; concurrent resolvers are unchanged.
    await session.execute(text("LOCK TABLE tags IN EXCLUSIVE MODE NOWAIT"))


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


async def resolve_tags(session: AsyncSession, names: Sequence[str]) -> list[Tag]:
    """Resolve bounded batches, ordering inserts and shared locks by exact name."""
    ordered_names = sorted(set(names))
    entities: list[Tag] = []
    for offset in range(0, len(ordered_names), _RESOLVE_BATCH_SIZE):
        batch = ordered_names[offset : offset + _RESOLVE_BATCH_SIZE]
        await session.execute(
            insert(Tag)
            .values([{"name": name} for name in batch])
            .on_conflict_do_nothing(index_elements=[Tag.name])
        )
        # DB collation need not match Python's name order. Lock rows in the same
        # explicit order used for VALUES, independent of the database locale.
        entities.extend(
            await session.scalars(
                select(Tag)
                .where(Tag.name.in_(batch))
                .order_by(
                    case(
                        {name: index for index, name in enumerate(batch)},
                        value=Tag.name,
                    )
                )
                .with_for_update(read=True)
                .execution_options(populate_existing=True)
            )
        )
    return entities


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
