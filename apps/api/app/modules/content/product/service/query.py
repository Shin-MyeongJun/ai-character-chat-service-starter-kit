from app.modules.content.product import repository, types
from app.modules.content.product.mapper.persistence import to_info


async def get_product(session, *, product_id, owner_id) -> types.ProductInfo:
    return to_info(await repository.owned(session, product_id, owner_id))


async def list_products(
    session, *, owner_id, offset=0, limit=50
) -> list[types.ProductInfo]:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid pagination.")
    return [
        to_info(row)
        for row in await repository.list_owned(
            session, owner_id, offset=offset, limit=limit
        )
    ]
