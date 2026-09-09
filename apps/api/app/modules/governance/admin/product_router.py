from uuid import UUID

from fastapi import APIRouter

from app.modules.content.product.http import Owner, Session, errors
from app.modules.governance.admin import schemas
from app.modules.governance.admin.mapper.schema import AdminSchemaMapper
from app.modules.governance.admin.product_policy import moderate_product, set_expiry

router = APIRouter(prefix="/admin/products", tags=["product administration"])


@router.put(
    "/versions/{snapshot_id}/expiry", response_model=schemas.ExpiryChangedResponseDto
)
async def expiry(
    snapshot_id: UUID, body: schemas.ExpiryRequest, session: Session, owner: Owner
):
    value = AdminSchemaMapper.to_expiry(body)
    with errors():
        return AdminSchemaMapper.expiry_response(
            await set_expiry(
                session,
                snapshot_id=snapshot_id,
                actor_id=owner,
                expires_at=value.expires_at,
                reason=value.reason,
            )
        )


@router.put("/{product_id}/status", status_code=204)
async def status(
    product_id: UUID, body: schemas.StatusRequest, session: Session, owner: Owner
):
    value = AdminSchemaMapper.to_status(body)
    with errors():
        await moderate_product(
            session, product_id=product_id, actor_id=owner, status=value.status
        )
