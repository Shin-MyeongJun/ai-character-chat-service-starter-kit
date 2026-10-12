"""Dictionary persistence only; content connections belong to their modules."""

from app.db.models.tag import Tag
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert


async def get_tag(session, tag_id, *, exclusive=False):
    stmt = select(Tag).where(Tag.id == tag_id)
    stmt = stmt.with_for_update() if exclusive else stmt
    return await session.scalar(stmt.execution_options(populate_existing=True))


async def get_tag_by_name(session, name):
    return await session.scalar(select(Tag).where(Tag.name == name))


async def get_tags(session, tag_ids):
    if not tag_ids:
        return []
    return list(await session.scalars(select(Tag).where(Tag.id.in_(tag_ids))))


async def resolve_tag(session, name, description=None):
    # ON CONFLICT waits for concurrent inserts without poisoning the transaction.
    await session.execute(
        insert(Tag)
        .values(name=name, description=description)
        .on_conflict_do_nothing(index_elements=[Tag.name])
    )
    # Hold activity/name stable until the caller finishes writing its connections.
    return await session.scalar(
        select(Tag)
        .where(Tag.name == name)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )


async def update_tag(session, tag_id, name, description):
    return await session.scalar(
        update(Tag)
        .where(Tag.id == tag_id)
        .values(name=name, description=description)
        .returning(Tag)
        .execution_options(populate_existing=True)
    )


async def deactivate_tag(session, tag_id):
    return await session.scalar(
        update(Tag)
        .where(Tag.id == tag_id)
        .values(is_active=False)
        .returning(Tag)
        .execution_options(populate_existing=True)
    )
