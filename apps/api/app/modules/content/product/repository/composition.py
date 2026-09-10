from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStartSet,
)


async def replace_product_composition(session, product_id, value) -> None:
    existing_chars = {
        c.character_id: c
        for c in await session.scalars(
            select(ProductCharacter).where(ProductCharacter.product_id == product_id)
        )
    }
    existing_books = {
        b.lorebook_id: b
        for b in await session.scalars(
            select(ProductLorebook).where(ProductLorebook.product_id == product_id)
        )
    }
    await session.execute(
        delete(ProductLorebookCharacter).where(
            ProductLorebookCharacter.product_id == product_id
        )
    )
    for cid, row in existing_chars.items():
        row.is_primary = False
        if cid not in {c.character_id for c in value.characters}:
            await session.delete(row)
    for bid, row in existing_books.items():
        if bid not in {b.lorebook_id for b in value.lorebooks}:
            await session.delete(row)
    await session.flush()
    character_map = {}
    for order, c in enumerate(value.characters):
        row = existing_chars.get(c.character_id)
        if row is None:
            row = ProductCharacter(
                id=uuid4(), product_id=product_id, character_id=c.character_id
            )
            session.add(row)
        row.is_primary, row.role_order, row.role_name = (
            c.is_primary,
            order,
            c.role_name,
        )
        character_map[c.character_id] = row.id
    books = []
    for b in value.lorebooks:
        row = existing_books.get(b.lorebook_id)
        if row is None:
            row = ProductLorebook(
                id=uuid4(), product_id=product_id, lorebook_id=b.lorebook_id
            )
            session.add(row)
        row.scope, row.role, row.priority, row.is_required = (
            b.scope,
            b.role,
            b.priority,
            b.is_required,
        )
        books.append((row, b))
    await session.flush()
    for row, b in books:
        for cid in b.character_ids:
            session.add(
                ProductLorebookCharacter(
                    product_id=product_id,
                    product_character_id=character_map[cid],
                    product_lorebook_id=row.id,
                )
            )
    await session.flush()


@dataclass(frozen=True)
class ProductCompositionRow:
    characters: list[ProductCharacter]
    books: list[ProductLorebook]
    links: list[ProductLorebookCharacter]


async def get_product_composition(session, product_id) -> ProductCompositionRow:
    characters = list(
        await session.scalars(
            select(ProductCharacter)
            .where(ProductCharacter.product_id == product_id)
            .order_by(ProductCharacter.role_order, ProductCharacter.id)
        )
    )
    books = list(
        await session.scalars(
            select(ProductLorebook)
            .where(ProductLorebook.product_id == product_id)
            .order_by(ProductLorebook.priority.desc(), ProductLorebook.id)
        )
    )
    links = list(
        await session.scalars(
            select(ProductLorebookCharacter).where(
                ProductLorebookCharacter.product_id == product_id
            )
        )
    )
    return ProductCompositionRow(characters, books, links)


async def set_product_settings(session, product_id, value, entries) -> None:
    product = await session.get(Product, product_id)
    product.default_model_id = value.model_id
    product.reasoning_effort = value.reasoning_effort
    product.replacement_policy = {
        "scope": value.replacement_scope,
        "model_ids": [str(i) for i in value.replacement_model_ids],
        "unavailable": value.unavailable_policy,
    }
    await session.execute(
        delete(ProductStartSet).where(ProductStartSet.product_id == product_id)
    )
    by_id = {e.id: e for e in entries}
    for order, entry_id in enumerate(value.start_entry_ids):
        session.add(
            ProductStartSet(
                product_id=product_id,
                lorebook_id=by_id[entry_id].lorebook_id,
                entry_id=entry_id,
                sort_order=order,
            )
        )
    await session.flush()


async def list_product_start_sets(session, product_id):
    return list(
        await session.scalars(
            select(ProductStartSet).where(ProductStartSet.product_id == product_id)
        )
    )
