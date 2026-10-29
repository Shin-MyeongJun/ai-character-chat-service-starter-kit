"""Persist a product's editable studio document and revision."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import ProductStudioDraft
from app.modules.content.product import types as Types


async def get_studio_draft(
    session: AsyncSession, product_id: UUID, *, lock: bool = False
) -> ProductStudioDraft | None:
    stmt = select(ProductStudioDraft).where(ProductStudioDraft.product_id == product_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    # The SELECT projects one ProductStudioDraft; scalar erases that type in its stub.
    draft: ProductStudioDraft | None = await session.scalar(stmt)
    return draft


async def save_studio_draft(
    session: AsyncSession,
    product_id: UUID,
    revision: int,
    digest: str,
    document: Types.ProductJsonObject,
    existing: ProductStudioDraft | None,
) -> ProductStudioDraft:
    if existing is None:
        existing = ProductStudioDraft(
            product_id=product_id,
            revision=revision,
            content_digest=digest,
            document=document,
        )
        session.add(existing)
    else:
        existing.revision = revision
        existing.content_digest = digest
        existing.document = document
    await session.flush()
    await session.refresh(existing)
    return existing


async def mark_studio_publication(
    session: AsyncSession,
    row: ProductStudioDraft | None,
    digest: str | None,
    release: Types.ProductJsonObject,
) -> None:
    # The service validated the mapped Info while holding this draft's row lock.
    assert row is not None, "Locked studio draft disappeared."
    row.publication_digest = digest
    row.publication_release = release
    await session.flush()
