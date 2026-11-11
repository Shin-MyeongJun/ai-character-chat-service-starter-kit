from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product_album import ProductImageUnlock


async def insert_image_unlocks(
    session: AsyncSession,
    account_id: UUID,
    product_id: UUID,
    image_item_ids: Sequence[UUID],
) -> None:
    statement = insert(ProductImageUnlock).values(
        [
            {
                "account_id": account_id,
                "product_id": product_id,
                "image_item_id": item_id,
            }
            for item_id in image_item_ids
        ]
    )
    await session.execute(
        statement.on_conflict_do_nothing(
            index_elements=[
                ProductImageUnlock.account_id,
                ProductImageUnlock.product_id,
                ProductImageUnlock.image_item_id,
            ]
        )
    )


async def list_image_unlocks(
    session: AsyncSession,
    account_id: UUID,
    product_id: UUID,
    image_item_ids: Sequence[UUID],
) -> Sequence[ProductImageUnlock]:
    return (
        await session.scalars(
            select(ProductImageUnlock).where(
                ProductImageUnlock.account_id == account_id,
                ProductImageUnlock.product_id == product_id,
                ProductImageUnlock.image_item_id.in_(image_item_ids),
            )
        )
    ).all()
