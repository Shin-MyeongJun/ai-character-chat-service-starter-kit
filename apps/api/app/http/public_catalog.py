"""Public detail for approved, published products in the catalog."""

from uuid import UUID

from fastapi import APIRouter

from app.http.dependencies import Session, errors
from app.modules.content.product import schemas as Schemas
from app.modules.content.product import types as Types
from app.modules.content.product.mapper.schema import ProductSchemaMapper
from app.modules.content.product.service.views.notices import get_published_product

router = APIRouter(prefix="/products/catalog", tags=["products"])


@router.get("/{product_id}", response_model=Schemas.PublishedProductInfoResponseDto)
async def get_catalog_product(product_id: UUID, session: Session):
    with errors():
        return ProductSchemaMapper.published_view_to_response(
            await get_published_product(
                session, Types.PublishedProductCommand(product_id=product_id, user_id=None)
            )
        )
