from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.identity import User
from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot, ProductSnapshotPolicyChange
from app.modules.governance.admin.types import ExpiryChanged


async def require_admin(session, actor_id):
    actor = await session.get(User, actor_id)
    if actor is None or actor.role != "admin" or actor.status != "active":
        raise LookupError("Administrative operation unavailable.")


async def set_expiry(
    session, *, snapshot_id, actor_id, expires_at, reason
) -> ExpiryChanged:
    if not reason.strip() or len(reason) > 2000:
        raise ValueError("Reason must contain 1–2000 characters.")
    if expires_at is not None and (
        expires_at.tzinfo is None or expires_at.utcoffset() is None
    ):
        raise ValueError("Expiry must include a timezone.")
    async with session.begin():
        await require_admin(session, actor_id)
        snapshot = await session.get(ProductSnapshot, snapshot_id, with_for_update=True)
        if snapshot is None:
            raise LookupError("Version not found.")
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
        return ExpiryChanged(
            snapshot_id=snapshot_id, expires_at=expires_at, reason=reason
        )


async def moderate_product(session, *, product_id, actor_id, status) -> None:
    if status not in ("approved", "rejected", "draft"):
        raise ValueError("Invalid product status.")
    async with session.begin():
        await require_admin(session, actor_id)
        product = await session.get(Product, product_id, with_for_update=True)
        if product is None:
            raise LookupError("Product not found.")
        product.status = status
        await session.flush()


async def ensure_available(session, snapshot_id, *, now=None):
    snapshot = await session.scalar(
        select(ProductSnapshot)
        .where(ProductSnapshot.id == snapshot_id)
        .execution_options(populate_existing=True)
    )
    if snapshot is None:
        raise LookupError("Version not found.")
    if snapshot.expires_at is not None and snapshot.expires_at <= (
        now or datetime.now(UTC)
    ):
        raise ValueError(
            "Version expired. History and memories are preserved; choose another version."
        )
    return snapshot
