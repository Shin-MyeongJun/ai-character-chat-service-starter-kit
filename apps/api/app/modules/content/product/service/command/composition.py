from app.db.transaction import use_case_transaction
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.service import query as QueryService
from app.modules.content.product.service.query.composition import get_composition


def _validate_composition(value: Types.ProductCompositionInfo):
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
        if b.scope not in ("all", "selected") or b.role not in (
            "main",
            "detail",
            "rule",
            "optional",
        ):
            raise ValueError("Invalid lorebook settings.")
        if not -(2**31) <= b.priority < 2**31:
            raise ValueError("Invalid priority.")
        if (
            b.scope == "all"
            and b.character_ids
            or (b.scope == "selected" and (not b.character_ids))
        ):
            raise ValueError("Selected scope requires targets; all scope has none.")
        if len(set(b.character_ids)) != len(b.character_ids) or not set(
            b.character_ids
        ) <= set(characters):
            raise ValueError("Targets must be distinct characters in this product.")


async def replace_composition(
    session, command: Types.ReplaceCompositionCommand
) -> Types.ProductCompositionInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    value = command.value
    _validate_composition(value)
    async with use_case_transaction(session):
        await QueryService.get_owned_product(
            session, Types.OwnedProductCommand(product_id, owner_id, lock=True)
        )
        await CharacterQueryService.get_owned_characters(
            session,
            CharacterTypes.GetOwnedCharactersCommand(
                tuple(c.character_id for c in value.characters), owner_id, lock=True
            ),
        )
        await LorebookQueryService.get_owned_lorebooks(
            session,
            LorebookTypes.GetOwnedLorebooksCommand(
                tuple(b.lorebook_id for b in value.lorebooks), owner_id, lock=True
            ),
        )
        await Repository.replace_product_composition(session, product_id, value)
        return value


__all__ = ["get_composition"]
