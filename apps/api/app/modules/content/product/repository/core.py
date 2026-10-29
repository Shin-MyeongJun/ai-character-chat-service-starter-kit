# 상품 목록은 owner 필터와 created_at/id 내림차순 offset 페이지다.
# get_owned_product(lock=True)는 FOR UPDATE, get_product(lock=True)는 공유 잠금 FOR SHARE다.
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Row, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.product import (
    Product,
)
from app.db.models.snapshot.product import (
    ProductSnapshot,
)
from app.db.models.tag import ProductTag
from app.modules.content.product import types as Types

CatalogRow = Row[tuple[Product, ProductSnapshot]]


def _owned_conditions(owner_id: UUID, search: str) -> list[ColumnElement[bool]]:
    """Keep owner counts and pages scoped identically; search metacharacters are literal."""
    conditions: list[ColumnElement[bool]] = [Product.owner_id == owner_id]
    if search:
        conditions.append(
            or_(
                Product.title.icontains(search, autoescape=True),
                Product.description.icontains(search, autoescape=True),
            )
        )
    return conditions


async def count_owned(
    session: AsyncSession, owner_id: UUID, *, search: str = ""
) -> int:
    """Count every matching owned work, including drafts and private works."""
    count = await session.scalar(
        select(func.count())
        .select_from(Product)
        .where(*_owned_conditions(owner_id, search))
    )
    # COUNT without GROUP BY always yields one non-null row, including zero.
    assert count is not None
    return count


async def list_owned(
    session: AsyncSession,
    owner_id: UUID,
    *,
    offset: int = 0,
    limit: int = 50,
    search: str = "",
) -> list[Product]:
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


async def list_catalog(
    session: AsyncSession,
    *,
    limit: int,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
    search: str = "",
    tag_id: UUID | None = None,
) -> list[CatalogRow]:
    """Filter published text and current public tag links before the keyset boundary."""
    stmt = (
        select(Product, ProductSnapshot)
        .join(ProductSnapshot, Product.latest_snapshot_id == ProductSnapshot.id)
        .where(
            Product.status == "approved",
            Product.visibility == "public",
            or_(
                ProductSnapshot.expires_at.is_(None),
                ProductSnapshot.expires_at > datetime.now(UTC),
            ),
        )
    )
    if search:
        stmt = stmt.where(
            or_(
                ProductSnapshot.snapshot_data["title"].astext.icontains(
                    search, autoescape=True
                ),
                ProductSnapshot.snapshot_data["description"].astext.icontains(
                    search, autoescape=True
                ),
            )
        )
    if tag_id is not None:
        stmt = stmt.where(
            exists().where(
                ProductTag.product_id == Product.id, ProductTag.tag_id == tag_id
            )
        )
    if cursor_created_at is not None:
        stmt = stmt.where(
            or_(
                Product.created_at < cursor_created_at,
                and_(Product.created_at == cursor_created_at, Product.id < cursor_id),
            )
        )
    return list(
        (
            await session.execute(
                stmt.order_by(Product.created_at.desc(), Product.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    )


async def list_catalog_tag_ids(session: AsyncSession) -> tuple[UUID, ...]:
    """Read only public tag links belonging to currently listable published products."""
    return tuple(
        await session.scalars(
            select(ProductTag.tag_id)
            .join(Product, Product.id == ProductTag.product_id)
            .join(ProductSnapshot, ProductSnapshot.id == Product.latest_snapshot_id)
            .where(
                Product.status == "approved",
                Product.visibility == "public",
                or_(
                    ProductSnapshot.expires_at.is_(None),
                    ProductSnapshot.expires_at > datetime.now(UTC),
                ),
            )
            .distinct()
        )
    )


async def save_product(session: AsyncSession, entity: Product) -> Product:
    session.add(entity)
    await session.flush()
    await session.refresh(entity)
    return entity


async def get_owned_product(
    session: AsyncSession, product_id: UUID, owner_id: UUID, *, lock: bool = False
) -> Product | None:
    stmt = select(Product).where(Product.id == product_id, Product.owner_id == owner_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    # The single-entity projection determines scalar's result type.
    entity: Product | None = await session.scalar(stmt)
    return entity


async def get_product(
    session: AsyncSession, product_id: UUID, *, lock: bool = False
) -> Product | None:
    stmt = select(Product).where(Product.id == product_id)
    if lock:
        stmt = stmt.with_for_update(read=True)
    entity: Product | None = await session.scalar(stmt)
    return entity


async def get_product_for_update(
    session: AsyncSession, product_id: UUID
) -> Product | None:
    entity: Product | None = await session.scalar(
        select(Product)
        .where(Product.id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return entity


async def create_product(
    session: AsyncSession,
    owner_id: UUID,
    value: Types.ProductProfileCommand,
    *,
    product_id: UUID | None = None,
) -> Product:
    return await save_product(
        session,
        Product(
            **({"id": product_id} if product_id is not None else {}),
            owner_id=owner_id,
            status="draft",
            title=value.title,
            description=value.description,
            opening_message=value.opening_message,
            visibility=value.visibility,
        ),
    )


async def update_product(
    session: AsyncSession,
    product_id: UUID,
    owner_id: UUID,
    value: Types.ProductProfileCommand,
) -> Product | None:
    entity = await get_owned_product(session, product_id, owner_id, lock=True)
    if entity is None:
        return None
    entity.title = value.title
    entity.description = value.description
    entity.opening_message = value.opening_message
    entity.visibility = value.visibility
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


async def set_product_status(
    session: AsyncSession, product_id: UUID, status: str
) -> None:
    product = await session.get(Product, product_id, with_for_update=True)
    # The service holds a lock on this existing product in the same transaction.
    assert product is not None, "Locked product disappeared."
    product.status = status
    await session.flush()
