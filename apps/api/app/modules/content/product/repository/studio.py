"""Persist a product's editable studio document and revision."""

from sqlalchemy import select

from app.db.models.product import ProductStudioDraft


async def get_studio_draft(session, product_id, *, lock=False):
    stmt = select(ProductStudioDraft).where(ProductStudioDraft.product_id == product_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def save_studio_draft(session, product_id, revision, digest, document, existing):
    if existing is None:
        existing = ProductStudioDraft(
            product_id=product_id, revision=revision,
            content_digest=digest, document=document,
        )
        session.add(existing)
    else:
        existing.revision = revision
        existing.content_digest = digest
        existing.document = document
    await session.flush()
    await session.refresh(existing)
    return existing


async def mark_studio_publication(session, row, digest, release):
    row.publication_digest = digest
    row.publication_release = release
    await session.flush()
