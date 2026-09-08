from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product


async def owned(session: AsyncSession, product_id: UUID, owner_id: UUID, *, lock=False):
    stmt = select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    if lock:
        stmt = stmt.with_for_update()
    result = await session.scalar(stmt)
    if result is None:
        raise LookupError("Product not found.")
    return result


async def list_owned(session: AsyncSession, owner_id: UUID, *, offset=0, limit=50):
    return list(await session.scalars(select(Product).where(Product.owner_id == owner_id)
        .order_by(Product.created_at.desc(), Product.id.desc())
        .offset(offset).limit(limit)))


async def save(session: AsyncSession, entity):
    session.add(entity)
    await session.flush()
    return entity
