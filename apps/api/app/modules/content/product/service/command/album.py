from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import types as Types
from app.modules.content.product.repository import album as AlbumRepository


async def unlock_product_images(
    session: AsyncSession, command: Types.UnlockProductImagesCommand
) -> None:
    """Record already validated occurrences within the caller's transaction."""
    # Consistent key order prevents overlapping batches from locking in reverse order.
    image_item_ids = sorted(set(command.image_item_ids))
    if image_item_ids:
        await AlbumRepository.insert_image_unlocks(
            session, command.account_id, command.product_id, image_item_ids
        )
