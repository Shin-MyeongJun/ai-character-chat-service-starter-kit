from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import types as Types
from app.modules.content.product.mapper import album as AlbumMapper
from app.modules.content.product.repository import album as AlbumRepository
from app.modules.content.product.service import query as QueryService


async def _get_latest_album_snapshot(
    session: AsyncSession, command: Types.GetProductAlbumCommand
) -> Types.ProductSnapshotInfo | None:
    product = await QueryService.get_accessible_product(
        session,
        Types.GetAccessibleProductCommand(
            product_id=command.product_id, user_id=command.account_id
        ),
    )
    if product.latest_snapshot_id is None:
        return None
    snapshot = await QueryService.get_product_snapshot(
        session, Types.ProductSnapshotCommand(snapshot_id=product.latest_snapshot_id)
    )
    if snapshot.product_id != command.product_id:
        return None
    if snapshot.expires_at is not None and snapshot.expires_at <= datetime.now(UTC):
        return None
    return snapshot


async def get_product_album(
    session: AsyncSession, command: Types.GetProductAlbumCommand
) -> Types.ProductAlbumInfo:
    snapshot = await _get_latest_album_snapshot(session, command)
    if snapshot is None:
        return Types.ProductAlbumInfo(command.product_id, None, ())
    images = tuple(
        AlbumMapper.snapshot_image_item_to_info(item)
        for item in snapshot.snapshot_data.get("chat_image_items", [])
    )
    if not images:
        return Types.ProductAlbumInfo(command.product_id, snapshot.id, ())
    rows = await AlbumRepository.list_image_unlocks(
        session,
        command.account_id,
        command.product_id,
        [image.image_item_id for image in images],
    )
    unlocked_at_by_item_id = AlbumMapper.image_unlock_entities_to_times(rows)
    items: list[
        Types.LockedProductAlbumItemInfo | Types.UnlockedProductAlbumItemInfo
    ] = []
    for image in images:
        unlocked_at = unlocked_at_by_item_id.get(image.image_item_id)
        if unlocked_at is None:
            items.append(Types.LockedProductAlbumItemInfo(image.image_item_id))
        else:
            items.append(Types.UnlockedProductAlbumItemInfo(image, unlocked_at))
    return Types.ProductAlbumInfo(command.product_id, snapshot.id, tuple(items))


async def authorize_product_album_file(
    session: AsyncSession, command: Types.ReadProductAlbumFileCommand
) -> Types.ProductFileReferenceCommand:
    snapshot = await _get_latest_album_snapshot(
        session,
        Types.GetProductAlbumCommand(
            product_id=command.product_id, account_id=command.account_id
        ),
    )
    if snapshot is None or not any(
        item["image_item_id"] == str(command.image_item_id)
        and item["file_version_id"] == str(command.file_version_id)
        for item in snapshot.snapshot_data.get("chat_image_items", [])
    ):
        raise LookupError("Album file not found.")
    rows = await AlbumRepository.list_image_unlocks(
        session, command.account_id, command.product_id, (command.image_item_id,)
    )
    if command.image_item_id not in AlbumMapper.image_unlock_entities_to_times(rows):
        raise LookupError("Album file not found.")
    return Types.ProductFileReferenceCommand(
        product_id=command.product_id,
        file_version_id=command.file_version_id,
        kind="snapshot",
        reference_id=snapshot.id,
    )
