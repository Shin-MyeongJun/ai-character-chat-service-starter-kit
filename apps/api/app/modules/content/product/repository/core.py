# 상품 목록은 owner 필터와 created_at/id 내림차순 offset 페이지다.
# get_owned_product(lock=True)는 FOR UPDATE, get_product(lock=True)는 공유 잠금 FOR SHARE다.
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import (
    Product,
)
from app.db.models.snapshot.product import (
    ProductSnapshot,
)


async def list_owned(session: AsyncSession, owner_id: UUID, *, offset=0, limit=50):
    return list(
        await session.scalars(
            select(Product)
            .where(Product.owner_id == owner_id)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )


async def save_product(session: AsyncSession, entity):
    session.add(entity)
    await session.flush()
    await session.refresh(entity)
    return entity


async def get_owned_product(
    session: AsyncSession, product_id: UUID, owner_id: UUID, *, lock=False
):
    stmt = select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def get_product(session: AsyncSession, product_id: UUID, *, lock=False):
    stmt = select(Product).where(Product.id == product_id)
    if lock:
        stmt = stmt.with_for_update(read=True)
    return await session.scalar(stmt)


async def create_product(session: AsyncSession, owner_id: UUID, value):
    return await save_product(
        session, Product(owner_id=owner_id, status="draft", **asdict(value))
    )


async def update_product(
    session: AsyncSession, product_id: UUID, owner_id: UUID, value
):
    entity = await get_owned_product(session, product_id, owner_id, lock=True)
    if entity is None:
        return None
    for key, field in asdict(value).items():
        setattr(entity, key, field)
    return await save_product(session, entity)


async def has_product_snapshot(session: AsyncSession, product_id: UUID) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(ProductSnapshot.product_id == product_id))
        )
    )


async def delete_product(
    session: AsyncSession, product_id: UUID, owner_id: UUID
) -> None:
    entity = await get_owned_product(session, product_id, owner_id, lock=True)
    if entity is not None:
        await session.delete(entity)


async def set_product_status(session, product_id, status) -> None:
    product = await session.get(Product, product_id, with_for_update=True)
    product.status = status
    await session.flush()
