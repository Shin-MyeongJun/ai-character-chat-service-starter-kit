from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.identity import User
from app.db.models.character import Character
from app.db.models.lorebook import Lorebook
from app.db.models.product import Product, ProductCharacter, ProductLorebook, ProductLorebookCharacter
from app.modules.content.product.service import command, composition
from app.modules.content.product.types import ProductWrite, Composition, CharacterSelection, LorebookSelection

pytestmark = pytest.mark.asyncio


async def seed(db):
    async with db.begin():
        owner = User(id=uuid4(), email=f'{uuid4()}@test.local')
        db.add(owner)
        await db.flush()
        c = Character(id=uuid4(), owner_id=owner.id, name='C', persona_prompt='P')
        b = Lorebook(id=uuid4(), owner_id=owner.id, title='B')
        db.add_all([c,b])
    return owner,c,b


async def test_composition_ownership_and_cross_product_fk(db):
    owner,c,b = await seed(db)
    p = await command.create_product(db, owner_id=owner.id, value=ProductWrite('P'))
    value = Composition((CharacterSelection(c.id, True),), (LorebookSelection(b.id, 'selected', (c.id,)),))
    assert await composition.replace_composition(db, product_id=p.id, owner_id=owner.id, value=value) == value
    with pytest.raises(LookupError):
        await composition.replace_composition(db, product_id=p.id, owner_id=uuid4(), value=value)
    async with db.begin():
        foreign = Product(id=uuid4(), owner_id=owner.id, title='foreign')
        db.add(foreign)
        await db.flush()
        other = ProductCharacter(id=uuid4(), product_id=foreign.id, character_id=c.id)
        db.add(other)
        await db.flush()
        target = await db.scalar(select(ProductLorebook).where(ProductLorebook.product_id == p.id))
        with pytest.raises(IntegrityError):
            async with db.begin_nested():
                db.add(ProductLorebookCharacter(product_id=p.id, product_character_id=other.id, product_lorebook_id=target.id))
                await db.flush()


async def test_foreign_content_cannot_be_added(db):
    owner,c,b = await seed(db)
    other,_,_ = await seed(db)
    p = await command.create_product(db, owner_id=other.id, value=ProductWrite('P'))
    with pytest.raises(LookupError):
        await composition.replace_composition(db, product_id=p.id, owner_id=other.id, value=Composition((CharacterSelection(c.id),), ()))
