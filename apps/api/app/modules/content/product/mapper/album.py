from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from app.db.models.product_album import ProductImageUnlock
from app.modules.content.product import types as Types


def image_unlock_entities_to_times(
    entities: Iterable[ProductImageUnlock],
) -> dict[UUID, datetime]:
    return {entity.image_item_id: entity.unlocked_at for entity in entities}


def snapshot_image_item_to_info(
    item: Types.ProductJsonObject,
) -> Types.ProductAlbumImageInfo:
    image_item_id = item["image_item_id"]
    file_version_id = item["file_version_id"]
    alt = item["alt"]
    # The publication builder stores canonical UUID strings and validated alt text.
    assert isinstance(image_item_id, str)
    assert isinstance(file_version_id, str)
    assert isinstance(alt, str)
    return Types.ProductAlbumImageInfo(UUID(image_item_id), UUID(file_version_id), alt)
