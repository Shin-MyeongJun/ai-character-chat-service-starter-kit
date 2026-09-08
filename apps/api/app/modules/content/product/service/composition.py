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
        await session.execute(delete(ProductLorebook).where(ProductLorebook.product_id == product_id))
        await session.execute(delete(ProductCharacter).where(ProductCharacter.product_id == product_id))
        character_map = {}
        for order, c in enumerate(value.characters):
            row = ProductCharacter(id=uuid4(), product_id=product_id, character_id=c.character_id, is_primary=c.is_primary, role_order=order, role_name=c.role_name)
            session.add(row)
            character_map[c.character_id] = row.id
        books = []
        for b in value.lorebooks:
            row = ProductLorebook(id=uuid4(), product_id=product_id, lorebook_id=b.lorebook_id, scope=b.scope, role=b.role, priority=b.priority, is_required=b.is_required)
            session.add(row)
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
