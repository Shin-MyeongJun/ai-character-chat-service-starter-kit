# 상품 목록은 owner 필터와 created_at/id 내림차순 offset 페이지다.
# get_owned_product(lock=True)는 FOR UPDATE, get_product(lock=True)는 공유 잠금 FOR SHARE다.
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import (
    Product,
)
from app.db.models.snapshot.product import (
    ProductSnapshot,
)
from app.db.models.tag import ProductTag


def _owned_conditions(owner_id, search):
    """Keep owner counts and pages scoped identically; search metacharacters are literal."""
    conditions = [Product.owner_id == owner_id]
    if search:
        conditions.append(or_(Product.title.icontains(search, autoescape=True), Product.description.icontains(search, autoescape=True)))
    return conditions


async def count_owned(session, owner_id, *, search="") -> int:
    """Count every matching owned work, including drafts and private works."""
    return await session.scalar(select(func.count()).select_from(Product).where(*_owned_conditions(owner_id, search)))


async def list_owned(session: AsyncSession, owner_id: UUID, *, offset=0, limit=50, search=""):
    """Search before pagination with a deterministic creation-time/ID tie breaker."""
    return list(
        await session.scalars(
            select(Product)
            .where(*_owned_conditions(owner_id, search))
            .order_by(Product.created_at.desc(), Product.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )


async def list_catalog(session: AsyncSession, *, limit, cursor_created_at=None, cursor_id=None, search="", tag_id=None):
    """Filter published text and current public tag links before the keyset boundary."""
    stmt = select(Product, ProductSnapshot).join(
        ProductSnapshot, Product.latest_snapshot_id == ProductSnapshot.id
    ).where(
        Product.status == "approved",
        Product.visibility == "public",
        or_(ProductSnapshot.expires_at.is_(None), ProductSnapshot.expires_at > datetime.now(UTC)),
    )
    if search:
        stmt = stmt.where(or_(ProductSnapshot.snapshot_data["title"].astext.icontains(search, autoescape=True), ProductSnapshot.snapshot_data["description"].astext.icontains(search, autoescape=True)))
    if tag_id is not None:
        stmt = stmt.where(exists().where(ProductTag.product_id == Product.id, ProductTag.tag_id == tag_id))
    if cursor_created_at is not None:
        stmt = stmt.where(or_(
            Product.created_at < cursor_created_at,
            and_(Product.created_at == cursor_created_at, Product.id < cursor_id),
        ))
    return list((await session.execute(
        stmt.order_by(Product.created_at.desc(), Product.id.desc()).limit(limit + 1)
    )).all())


async def list_catalog_tag_ids(session):
    """Read only public tag links belonging to currently listable published products."""
    return tuple(await session.scalars(select(ProductTag.tag_id).join(Product, Product.id == ProductTag.product_id).join(ProductSnapshot, ProductSnapshot.id == Product.latest_snapshot_id).where(Product.status == "approved", Product.visibility == "public", or_(ProductSnapshot.expires_at.is_(None), ProductSnapshot.expires_at > datetime.now(UTC))).distinct()))


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


async def get_product_for_update(session: AsyncSession, product_id: UUID):
    return await session.scalar(
        select(Product).where(Product.id == product_id).with_for_update().execution_options(populate_existing=True)
    )


async def create_product(session: AsyncSession, owner_id: UUID, value, *, product_id=None):
    return await save_product(
        session, Product(**({"id": product_id} if product_id is not None else {}), owner_id=owner_id, status="draft", **asdict(value))
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
