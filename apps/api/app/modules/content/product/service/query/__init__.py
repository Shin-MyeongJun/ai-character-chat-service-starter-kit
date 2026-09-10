from datetime import UTC, datetime

from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper


async def get_owned_product(
    session, command: Types.OwnedProductCommand
) -> Types.ProductStateInfo:
    row = await Repository.get_owned_product(
        session, command.product_id, command.owner_id, lock=command.lock
    )
    info = PersistenceMapper.product_entity_to_state_info(row)
    if info is None:
        raise LookupError("Product not found.")
    return info


async def get_product_snapshot(
    session, command: Types.ProductSnapshotCommand
) -> Types.ProductSnapshotInfo:
    row = await Repository.get_product_snapshot(
        session, command.snapshot_id, lock=command.lock
    )
    info = PersistenceMapper.product_snapshot_entity_to_info(row)
    if info is None:
        raise LookupError("Version not found.")
    return info


async def get_product(session, command: Types.GetProductCommand) -> Types.ProductInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    return await get_owned_product(
        session, Types.OwnedProductCommand(product_id, owner_id)
    )


async def list_products(
    session, command: Types.ListProductsCommand
) -> list[Types.ProductInfo]:
    owner_id = command.owner_id
    offset = command.offset
    limit = command.limit
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid pagination.")
    rows = await Repository.list_owned(session, owner_id, offset=offset, limit=limit)
    return PersistenceMapper.products_entities_to_info(rows)


async def ensure_snapshot_available(
    session, command: Types.ProductSnapshotCommand, *, now=None
) -> Types.ProductSnapshotInfo:
    snapshot = await get_product_snapshot(session, command)
    if snapshot.expires_at is not None and snapshot.expires_at <= (
        now or datetime.now(UTC)
    ):
        raise ValueError(
            "Version expired. History and memories are preserved; choose another version."
        )
    return snapshot


async def get_accessible_product(
    session, command: Types.GetAccessibleProductCommand
) -> Types.ProductStateInfo:
    product_id = command.product_id
    user_id = command.user_id
    lock = command.lock
    row = await Repository.get_product(session, product_id, lock=lock)
    product = PersistenceMapper.product_entity_to_state_info(row)
    if product is None or (
        product.owner_id != user_id
        and (product.status != "approved" or product.visibility == "private")
    ):
        raise LookupError("Product not found.")
    return product


async def list_product_releases(
    session, command: Types.ListProductReleasesCommand
) -> list[tuple[Types.ProductSnapshotInfo, Types.ReleaseNoteInfo | None]]:
    product_id = command.product_id
    after_version = command.after_version
    through_version = command.through_version
    rows = await Repository.list_product_release_rows(
        session, product_id, after_version, through_version
    )
    return PersistenceMapper.product_releases_rows_to_info(rows)


async def get_snapshot_composition(
    session, command: Types.ProductSnapshotCommand
) -> Types.SnapshotCompositionInfo:
    row = await Repository.get_snapshot_composition(session, command.snapshot_id)
    return PersistenceMapper.snapshot_composition_row_to_info(row)


async def get_product_state(
    session, command: Types.GetProductStateCommand
) -> Types.ProductStateInfo | None:
    product_id = command.product_id
    row = await Repository.get_product(session, product_id)
    return PersistenceMapper.product_entity_to_state_info(row)


async def ensure_available(
    session, command: Types.EnsureAvailableCommand
) -> Types.ProductSnapshotInfo:
    snapshot_id = command.snapshot_id
    now = command.now
    return await ensure_snapshot_available(
        session, Types.ProductSnapshotCommand(snapshot_id), now=now
    )
