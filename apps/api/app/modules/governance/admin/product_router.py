# 관리 API 입력을 상품 상태·버전 만료 Command로 변환한다. 실패는 공통 errors 경계에서 HTTP로 변환한다.
from uuid import UUID

from fastapi import APIRouter

from app.http.dependencies import Owner, Session, errors
from app.modules.governance.admin import schemas as Schemas
from app.modules.governance.admin import types as Types
from app.modules.governance.admin.mapper.schema import AdminSchemaMapper as SchemaMapper
from app.modules.governance.admin.service.command import moderate_product, set_expiry

router = APIRouter(prefix="/admin/products", tags=["product administration"])


@router.put(
    "/versions/{snapshot_id}/expiry", response_model=Schemas.ExpiryChangedResponseDto
)
async def expiry(
    snapshot_id: UUID, body: Schemas.ExpiryRequest, session: Session, owner: Owner
):
    value = SchemaMapper.expiry_request_to_command(body)
    with errors():
        return SchemaMapper.expiry_info_to_response(
            await set_expiry(
                session,
                Types.SetExpiryCommand(
                    snapshot_id=snapshot_id,
                    actor_id=owner,
                    expires_at=value.expires_at,
                    reason=value.reason,
                ),
            )
        )


@router.put("/{product_id}/status", status_code=204)
async def status(
    product_id: UUID, body: Schemas.StatusRequest, session: Session, owner: Owner
):
    value = SchemaMapper.status_request_to_command(body)
    with errors():
        await moderate_product(
            session,
            Types.ModerateProductCommand(
                product_id=product_id, actor_id=owner, status=value.status
            ),
        )
