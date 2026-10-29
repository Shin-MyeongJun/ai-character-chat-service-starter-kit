# 유지되는 원본 구성의 링크 ID는 재사용하고 제거된 구성과 대상 링크를 갱신한다.
# 주인공 플래그를 먼저 비우고 flush한 뒤 새 주인공을 지정해 중간 유일 제약 충돌을 피한다.
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import (
    Product,
    ProductCharacter,
    ProductLorebook,
    ProductLorebookCharacter,
    ProductStartSet,
)
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as Types


async def replace_product_composition(
    session: AsyncSession, product_id: UUID, value: Types.ProductCompositionInfo
) -> None:
    characters_by_source_id = {
        entity.character_id: entity
        for entity in await session.scalars(
            select(ProductCharacter).where(ProductCharacter.product_id == product_id)
        )
    }
    lorebooks_by_source_id = {
        entity.lorebook_id: entity
        for entity in await session.scalars(
            select(ProductLorebook).where(ProductLorebook.product_id == product_id)
        )
    }
    await session.execute(
        delete(ProductLorebookCharacter).where(
            ProductLorebookCharacter.product_id == product_id
        )
    )
    for character_id, character_entity in characters_by_source_id.items():
        character_entity.is_primary = False
        if character_id not in {
            selection.character_id for selection in value.characters
        }:
            await session.delete(character_entity)
    for lorebook_id, lorebook_entity in lorebooks_by_source_id.items():
        if lorebook_id not in {selection.lorebook_id for selection in value.lorebooks}:
            await session.delete(lorebook_entity)
    await session.flush()
    character_link_ids_by_source_id: dict[UUID, UUID] = {}
    for sort_order, character_selection in enumerate(value.characters):
        character_link = characters_by_source_id.get(character_selection.character_id)
        if character_link is None:
            character_link = ProductCharacter(
                id=uuid4(),
                product_id=product_id,
                character_id=character_selection.character_id,
            )
            session.add(character_link)
        (
            character_link.is_primary,
            character_link.role_order,
            character_link.role_name,
        ) = (
            character_selection.is_primary,
            sort_order,
            character_selection.role_name,
        )
        character_link_ids_by_source_id[character_selection.character_id] = (
            character_link.id
        )
    lorebook_links: list[tuple[ProductLorebook, Types.LorebookSelection]] = []
    for lorebook_selection in value.lorebooks:
        lorebook_link = lorebooks_by_source_id.get(lorebook_selection.lorebook_id)
        if lorebook_link is None:
            lorebook_link = ProductLorebook(
                id=uuid4(),
                product_id=product_id,
                lorebook_id=lorebook_selection.lorebook_id,
            )
            session.add(lorebook_link)
        (
            lorebook_link.scope,
            lorebook_link.role,
            lorebook_link.priority,
            lorebook_link.is_required,
        ) = (
            lorebook_selection.scope,
            lorebook_selection.role,
            lorebook_selection.priority,
            lorebook_selection.is_required,
        )
        lorebook_links.append((lorebook_link, lorebook_selection))
    await session.flush()
    for lorebook_link, lorebook_selection in lorebook_links:
        for character_id in lorebook_selection.character_ids:
            session.add(
                ProductLorebookCharacter(
                    product_id=product_id,
                    product_character_id=character_link_ids_by_source_id[character_id],
                    product_lorebook_id=lorebook_link.id,
                )
            )
    await session.flush()


@dataclass(frozen=True)
class ProductCompositionRow:
    characters: list[ProductCharacter]
    books: list[ProductLorebook]
    links: list[ProductLorebookCharacter]


async def get_product_composition(
    session: AsyncSession, product_id: UUID
) -> ProductCompositionRow:
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


async def set_product_settings(
    session: AsyncSession,
    product_id: UUID,
    value: Types.ProductSettingsInfo,
    entries: Sequence[LorebookTypes.LorebookEntryInfo],
) -> None:
    product = await session.get(Product, product_id)
    # The settings service holds the owned product lock in this transaction.
    assert product is not None, "Locked product disappeared."
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
    entries_by_id = {entry.id: entry for entry in entries}
    for sort_order, entry_id in enumerate(value.start_entry_ids):
        session.add(
            ProductStartSet(
                product_id=product_id,
                lorebook_id=entries_by_id[entry_id].lorebook_id,
                entry_id=entry_id,
                sort_order=sort_order,
            )
        )
    await session.flush()


async def list_product_start_sets(
    session: AsyncSession, product_id: UUID
) -> list[ProductStartSet]:
    return list(
        await session.scalars(
            select(ProductStartSet).where(ProductStartSet.product_id == product_id)
        )
    )
