# This module owns these connections; dictionary data is read through tag service.
from sqlalchemy import delete as tag_delete
from sqlalchemy import func
from sqlalchemy import select as tag_select
from sqlalchemy.dialects.postgresql import insert as tag_insert

from app.db.models.product import Product
from app.db.models.tag import ProductInternalTag, ProductTag


async def get_target_for_tag_access(session, target_id, *, lock=False):
    stmt = tag_select(Product).where(Product.id == target_id)
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt.execution_options(populate_existing=True))


async def list_public_tag_links(session, target_id):
    return list(
        await session.scalars(
            tag_select(ProductTag)
            .where(ProductTag.product_id == target_id)
            .order_by(ProductTag.sort_order, ProductTag.created_at, ProductTag.tag_id)
            .execution_options(populate_existing=True)
        )
    )


async def list_internal_tag_links(session, target_id):
    return list(
        await session.scalars(
            tag_select(ProductInternalTag)
            .where(ProductInternalTag.product_id == target_id)
            .order_by(ProductInternalTag.created_at, ProductInternalTag.tag_id)
            .execution_options(populate_existing=True)
        )
    )


async def replace_public_tag_links(session, target_id, tag_ids, actor_id):
    await session.execute(
        tag_delete(ProductTag).where(
            ProductTag.product_id == target_id, ProductTag.tag_id.not_in(tag_ids)
        )
    )
    for order, tag_id in enumerate(tag_ids):
        stmt = tag_insert(ProductTag).values(
            product_id=target_id, tag_id=tag_id, sort_order=order, assigned_by=actor_id
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[ProductTag.product_id, ProductTag.tag_id],
                set_={"sort_order": order},
            )
        )


async def remove_public_tag_link(session, target_id, tag_id):
    await session.execute(
        tag_delete(ProductTag).where(
            ProductTag.product_id == target_id, ProductTag.tag_id == tag_id
        )
    )


async def remove_internal_tag_links(session, target_id, tag_ids):
    await session.execute(
        tag_delete(ProductInternalTag).where(
            ProductInternalTag.product_id == target_id,
            ProductInternalTag.tag_id.in_(tag_ids),
        )
    )


async def set_internal_tag_link(session, target_id, tag_id, source, actor_id):
    stmt = tag_insert(ProductInternalTag).values(
        product_id=target_id, tag_id=tag_id, source=source, assigned_by=actor_id
    )
    values = {"source": source, "assigned_by": actor_id, "updated_at": func.now()}
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[ProductInternalTag.product_id, ProductInternalTag.tag_id],
            set_=values,
            where=(ProductInternalTag.source != "admin")
            if source == "system"
            else None,
        )
    )
