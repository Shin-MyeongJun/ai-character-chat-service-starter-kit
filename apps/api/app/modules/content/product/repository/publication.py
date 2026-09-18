# 발행마다 구성 슬롯·시작 항목은 새 스냅샷 행으로 만든다. 원본 링크 ID와 버전 링크 ID는 다르다.
# 버전 번호 MAX+1은 상위 상품 잠금을 전제로 한다. 만료 변경은 이전/신규 시각과 사유 이력을 남긴다.
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import (
    Product,
)
from app.db.models.snapshot.product import (
    ProductSnapshot,
    ProductSnapshotCharacter,
    ProductSnapshotLorebook,
    ProductSnapshotLorebookCharacter,
    ProductSnapshotPolicyChange,
    ProductSnapshotStartSet,
)


async def get_product_snapshot(session: AsyncSession, snapshot_id: UUID, *, lock=False):
    stmt = (
        select(ProductSnapshot)
        .where(ProductSnapshot.id == snapshot_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def set_product_snapshot_expiry(
    session, snapshot_id, actor_id, expires_at, reason
) -> None:
    snapshot = await session.get(ProductSnapshot, snapshot_id, with_for_update=True)
    session.add(
        ProductSnapshotPolicyChange(
            product_snapshot_id=snapshot.id,
            actor_id=actor_id,
            old_expires_at=snapshot.expires_at,
            new_expires_at=expires_at,
            reason=reason,
        )
    )
    snapshot.expires_at, snapshot.expiry_reason = expires_at, reason
    await session.flush()


async def create_product_snapshot(session, product_id, data):
    version = (
        await session.scalar(
            select(func.max(ProductSnapshot.version)).where(
                ProductSnapshot.product_id == product_id
            )
        )
        or 0
    ) + 1
    snapshot = ProductSnapshot(
        id=uuid4(),
        product_id=product_id,
        version=version,
        snapshot_schema_version=2,
        snapshot_data=data,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def add_snapshot_character(session, snapshot_id, component_id, value):
    row = ProductSnapshotCharacter(
        id=uuid4(),
        product_snapshot_id=snapshot_id,
        character_snapshot_id=component_id,
        role_order=value.role_order,
        role_name=value.role_name,
        is_primary=value.is_primary,
    )
    session.add(row)
    await session.flush()
    return row.id


async def add_snapshot_lorebook(session, snapshot_id, component_id, value):
    row = ProductSnapshotLorebook(
        id=uuid4(),
        product_snapshot_id=snapshot_id,
        lorebook_snapshot_id=component_id,
        role=value.role,
        priority=value.priority,
        is_required=value.is_required,
        scope=value.scope,
    )
    session.add(row)
    await session.flush()
    return row.id


async def add_snapshot_target(session, snapshot_id, character_id, lorebook_id) -> None:
    session.add(
        ProductSnapshotLorebookCharacter(
            product_snapshot_id=snapshot_id,
            product_character_id=character_id,
            product_lorebook_id=lorebook_id,
        )
    )
    await session.flush()


async def add_snapshot_start(
    session, snapshot_id, lorebook_id, entry, sort_order
) -> None:
    session.add(
        ProductSnapshotStartSet(
            product_snapshot_id=snapshot_id,
            product_lorebook_id=lorebook_id,
            source_entry_id=entry.id,
            title=entry.title,
            content=entry.content,
            sort_order=sort_order,
        )
    )
    await session.flush()


async def finish_product_snapshot(session, product_id, snapshot_id, data):
    snapshot = await session.get(ProductSnapshot, snapshot_id)
    snapshot.snapshot_data = data
    await session.flush()
    product = await session.get(Product, product_id)
    product.latest_snapshot_id = snapshot_id
    await session.flush()
    return snapshot


async def list_snapshot_character_ids(session, snapshot_id):
    return tuple(
        await session.scalars(
            select(ProductSnapshotCharacter.character_snapshot_id).where(
                ProductSnapshotCharacter.product_snapshot_id == snapshot_id
            )
        )
    )


@dataclass(frozen=True)
class SnapshotCompositionRow:
    characters: list[ProductSnapshotCharacter]
    books: list[ProductSnapshotLorebook]
    targets: list[ProductSnapshotLorebookCharacter]
    starts: list[ProductSnapshotStartSet]


async def get_snapshot_composition(session, snapshot_id) -> SnapshotCompositionRow:
    characters = list(
        await session.scalars(
            select(ProductSnapshotCharacter)
            .where(ProductSnapshotCharacter.product_snapshot_id == snapshot_id)
            .order_by(ProductSnapshotCharacter.role_order)
        )
    )
    books = list(
        await session.scalars(
            select(ProductSnapshotLorebook)
            .where(ProductSnapshotLorebook.product_snapshot_id == snapshot_id)
            .order_by(ProductSnapshotLorebook.priority.desc())
        )
    )
    targets = list(
        await session.scalars(
            select(ProductSnapshotLorebookCharacter).where(
                ProductSnapshotLorebookCharacter.product_snapshot_id == snapshot_id
            )
        )
    )
    starts = list(
        await session.scalars(
            select(ProductSnapshotStartSet)
            .where(ProductSnapshotStartSet.product_snapshot_id == snapshot_id)
            .order_by(ProductSnapshotStartSet.sort_order)
        )
    )
    return SnapshotCompositionRow(characters, books, targets, starts)
