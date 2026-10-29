"""Read a saved studio document only after checking product ownership."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService


async def get_studio_draft(
    session: AsyncSession, command: Types.GetStudioDraftCommand
) -> Types.StudioDraftInfo:
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id
        ),
    )
    row = await Repository.get_studio_draft(session, command.product_id)
    info = PersistenceMapper.studio_draft_entity_to_info(row)
    if info is None:
        raise LookupError("Studio draft not found.")
    return info


async def get_studio_draft_for_publication(
    session: AsyncSession, command: Types.GetStudioDraftCommand
) -> Types.StudioDraftInfo:
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id, lock=True
        ),
    )
    row = await Repository.get_studio_draft(session, command.product_id, lock=True)
    info = PersistenceMapper.studio_draft_entity_to_info(row)
    if info is None:
        raise LookupError("Studio draft not found.")
    return info
