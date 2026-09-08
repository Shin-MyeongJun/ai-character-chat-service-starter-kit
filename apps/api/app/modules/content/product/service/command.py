"""Commands own transactions; owner_id must come from trusted authentication."""
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.content.product import repository, types
from app.modules.content.product.mapper.persistence import to_info


def validate_profile(value: types.ProductWrite):
    if not value.title.strip() or len(value.title) > 200:
        raise ValueError("Title must contain 1–200 characters.")
    if value.visibility not in ("private", "public", "unlisted"):
        raise ValueError("Invalid visibility.")
    for field in (value.description, value.opening_message):
        if field is not None and len(field) > 20000:
            raise ValueError("Text exceeds 20000 characters.")


async def create_product(session: AsyncSession, *, owner_id: UUID, value: types.ProductWrite):
    validate_profile(value)
    async with session.begin():
        entity = Product(owner_id=owner_id, status="draft", **asdict(value))
        return to_info(await repository.save(session, entity))


async def update_product(session: AsyncSession, *, product_id: UUID, owner_id: UUID, value: types.ProductWrite):
    validate_profile(value)
    async with session.begin():
        entity = await repository.owned(session, product_id, owner_id, lock=True)
        for key, field in asdict(value).items():
            setattr(entity, key, field)
        return to_info(await repository.save(session, entity))


async def delete_product(session: AsyncSession, *, product_id: UUID, owner_id: UUID):
    async with session.begin():
        entity = await repository.owned(session, product_id, owner_id, lock=True)
        if await session.scalar(select(exists().where(ProductSnapshot.product_id == product_id))):
            raise ValueError("Published products must be retired, not deleted.")
        await session.delete(entity)
