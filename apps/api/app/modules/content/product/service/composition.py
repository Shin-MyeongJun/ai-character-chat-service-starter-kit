from uuid import uuid4
from sqlalchemy import delete, select
from app.db.models.character import Character
from app.db.models.lorebook import Lorebook
from app.db.models.product import ProductCharacter, ProductLorebook, ProductLorebookCharacter
from app.modules.content.product import repository, types


def validate(value: types.Composition):
    characters = [c.character_id for c in value.characters]
    lorebooks = [b.lorebook_id for b in value.lorebooks]
    if len(characters) > 100 or len(lorebooks) > 100:
        raise ValueError("At most 100 characters and lorebooks per product.")
    if len(set(characters)) != len(characters) or len(set(lorebooks)) != len(lorebooks):
        raise ValueError("Duplicate component.")
    if sum(c.is_primary for c in value.characters) > 1:
        raise ValueError("At most one primary character.")
    for c in value.characters:
        if c.role_name is not None and len(c.role_name) > 200:
            raise ValueError("Role name exceeds 200 characters.")
    for b in value.lorebooks:
        if b.scope not in ('all', 'selected') or b.role not in ('main', 'detail', 'rule', 'optional'):
            raise ValueError("Invalid lorebook settings.")
        if not -(2**31) <= b.priority < 2**31:
            raise ValueError("Invalid priority.")
        if b.scope == 'all' and b.character_ids or b.scope == 'selected' and not b.character_ids:
            raise ValueError("Selected scope requires targets; all scope has none.")
        if len(set(b.character_ids)) != len(b.character_ids) or not set(b.character_ids) <= set(characters):
            raise ValueError("Targets must be distinct characters in this product.")


async def replace_composition(session, *, product_id, owner_id, value: types.Composition):
    validate(value)
    async with session.begin():
        await repository.owned(session, product_id, owner_id, lock=True)
        for entity, ids in ((Character, [c.character_id for c in value.characters]), (Lorebook, [b.lorebook_id for b in value.lorebooks])):
            found = list(await session.scalars(select(entity.id).where(entity.id.in_(ids), entity.owner_id == owner_id).order_by(entity.id).with_for_update()))
            if len(found) != len(ids):
                raise LookupError("Owned component not found.")
        existing_chars = {c.character_id: c for c in await session.scalars(select(ProductCharacter).where(ProductCharacter.product_id == product_id))}
        existing_books = {b.lorebook_id: b for b in await session.scalars(select(ProductLorebook).where(ProductLorebook.product_id == product_id))}
        await session.execute(delete(ProductLorebookCharacter).where(ProductLorebookCharacter.product_id == product_id))
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
                row = ProductCharacter(id=uuid4(), product_id=product_id, character_id=c.character_id)
                session.add(row)
            row.is_primary, row.role_order, row.role_name = c.is_primary, order, c.role_name
            character_map[c.character_id] = row.id
        books = []
        for b in value.lorebooks:
            row = existing_books.get(b.lorebook_id)
            if row is None:
                row = ProductLorebook(id=uuid4(), product_id=product_id, lorebook_id=b.lorebook_id)
                session.add(row)
            row.scope, row.role, row.priority, row.is_required = b.scope, b.role, b.priority, b.is_required
            books.append((row, b))
        await session.flush()
        for row, b in books:
            for cid in b.character_ids:
                session.add(ProductLorebookCharacter(product_id=product_id, product_character_id=character_map[cid], product_lorebook_id=row.id))
        await session.flush()
        return value


async def get_composition(session, *, product_id, owner_id):
    await repository.owned(session, product_id, owner_id)
    characters = list(await session.scalars(select(ProductCharacter).where(ProductCharacter.product_id == product_id).order_by(ProductCharacter.role_order, ProductCharacter.id)))
    books = list(await session.scalars(select(ProductLorebook).where(ProductLorebook.product_id == product_id).order_by(ProductLorebook.priority.desc(), ProductLorebook.id)))
    links = list(await session.scalars(select(ProductLorebookCharacter).where(ProductLorebookCharacter.product_id == product_id)))
    ids = {c.id: c.character_id for c in characters}
    return types.Composition(
        tuple(types.CharacterSelection(c.character_id, c.is_primary, c.role_name) for c in characters),
        tuple(types.LorebookSelection(b.lorebook_id, b.scope, tuple(ids[t.product_character_id] for t in links if t.product_lorebook_id == b.id), b.role, b.priority, b.is_required) for b in books),
    )
