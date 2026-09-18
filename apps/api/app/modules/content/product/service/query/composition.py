# 소유 상품 확인 뒤 구성 링크를 원본 character/lorebook ID 중심의 값으로 반환한다.
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import query as QueryService


async def get_composition(
    session, command: Types.GetCompositionCommand
) -> Types.ProductCompositionInfo:
    product_id = command.product_id
    owner_id = command.owner_id
    await QueryService.get_owned_product(
        session, Types.OwnedProductCommand(product_id, owner_id)
    )
    row = await Repository.get_product_composition(session, product_id)
    return PersistenceMapper.product_composition_row_to_info(row)
