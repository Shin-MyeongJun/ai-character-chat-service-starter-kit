# 소유자 초안 조회·고정 버전 조회·접근 정책·만료 검사 경계. 버전 조회 자체는 사용자 인가를 하지 않는다.
# get_accessible_product는 소유자 또는 approved이면서 private이 아닌 상품을 허용한다.
# ensure_snapshot_available은 만료만 검사하며 상품 공개/심사 상태는 재검사하지 않는다.
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.tag import types as TagTypes


async def get_owned_product(
    session: AsyncSession, command: Types.OwnedProductCommand
) -> Types.ProductStateInfo:
    row = await Repository.get_owned_product(
        session, command.product_id, command.owner_id, lock=command.lock
    )
    info = PersistenceMapper.product_entity_to_state_info(row)
    if info is None:
        raise LookupError("Product not found.")
    return info


async def get_product_snapshot(
    session: AsyncSession, command: Types.ProductSnapshotCommand
) -> Types.ProductSnapshotInfo:
    row = await Repository.get_product_snapshot(
        session, command.snapshot_id, lock=command.lock
    )
    info = PersistenceMapper.product_snapshot_entity_to_info(row)
    if info is None:
        raise LookupError("Version not found.")
    return info


async def get_product(
    session: AsyncSession, command: Types.GetProductCommand
) -> Types.ProductInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    return await get_owned_product(
        session, Types.OwnedProductCommand(product_id=product_id, owner_id=owner_id)
    )


async def list_products(
    session: AsyncSession, command: Types.ListProductsCommand
) -> list[Types.ProductInfo]:
    """Return one server-searched owner page without changing the legacy array contract."""
    owner_id = command.owner_id
    offset = command.offset
    limit = command.limit
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid pagination.")
    if len(command.search) > 200:
        raise ValueError("Search is too long.")
    rows = await Repository.list_owned(
        session, owner_id, offset=offset, limit=limit, search=command.search.strip()
    )
    return PersistenceMapper.products_entities_to_info(rows)


async def list_catalog(
    session: AsyncSession, command: Types.ListCatalogCommand
) -> Types.CatalogPageInfo:
    """Apply the same published-text/tag conditions on every catalog page."""
    if len(command.search) > 200:
        raise ValueError("Search is too long.")
    if (
        not 1 <= command.limit <= 100
        or ((command.cursor_created_at is None) != (command.cursor_id is None))
        or (
            command.cursor_created_at is not None
            and command.cursor_created_at.utcoffset() is None
        )
    ):
        raise ValueError("Invalid catalog cursor or limit.")
    rows = await Repository.list_catalog(
        session,
        limit=command.limit,
        cursor_created_at=command.cursor_created_at,
        cursor_id=command.cursor_id,
        search=command.search.strip(),
        tag_id=command.tag_id,
    )
    return PersistenceMapper.catalog_entities_to_page_info(rows, command.limit)


async def count_products(
    session: AsyncSession, command: Types.ListProductsCommand
) -> int:
    """Count the same owner/search scope as list_products, independent of its page."""
    if len(command.search) > 200:
        raise ValueError("Search is too long.")
    return await Repository.count_owned(
        session, command.owner_id, search=command.search.strip()
    )


async def list_catalog_tags(session: AsyncSession) -> tuple[TagTypes.TagInfo, ...]:
    """Resolve only tag IDs that occur on listable products through the tag public API."""
    from app.modules.content.tag.service import query as TagQueryService

    tag_ids = await Repository.list_catalog_tag_ids(session)
    return tuple(
        sorted(
            await TagQueryService.get_tags(
                session, TagTypes.GetTagsCommand(tag_ids=tag_ids)
            ),
            key=lambda tag: (tag.name, tag.id),
        )
    )


async def ensure_snapshot_available(
    session: AsyncSession,
    command: Types.ProductSnapshotCommand,
    *,
    now: datetime | None = None,
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
    session: AsyncSession, command: Types.GetAccessibleProductCommand
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
    session: AsyncSession, command: Types.ListProductReleasesCommand
) -> list[tuple[Types.ProductSnapshotInfo, Types.ReleaseNoteInfo | None]]:
    product_id = command.product_id
    after_version = command.after_version
    through_version = command.through_version
    rows = await Repository.list_product_release_rows(
        session, product_id, after_version, through_version
    )
    return PersistenceMapper.product_releases_rows_to_info(rows)


async def get_snapshot_composition(
    session: AsyncSession, command: Types.ProductSnapshotCommand
) -> Types.SnapshotCompositionInfo:
    row = await Repository.get_snapshot_composition(session, command.snapshot_id)
    return PersistenceMapper.snapshot_composition_row_to_info(row)


async def get_product_state(
    session: AsyncSession, command: Types.GetProductStateCommand
) -> Types.ProductStateInfo | None:
    product_id = command.product_id
    row = await Repository.get_product(session, product_id)
    return PersistenceMapper.product_entity_to_state_info(row)


async def ensure_available(
    session: AsyncSession, command: Types.EnsureAvailableCommand
) -> Types.ProductSnapshotInfo:
    snapshot_id = command.snapshot_id
    now = command.now
    return await ensure_snapshot_available(
        session, Types.ProductSnapshotCommand(snapshot_id), now=now
    )
