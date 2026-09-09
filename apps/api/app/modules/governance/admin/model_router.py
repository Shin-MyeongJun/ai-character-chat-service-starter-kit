from uuid import UUID

from fastapi import APIRouter

from app.modules.content.product.http import Owner, Session, errors
from app.modules.governance.admin import schemas
from app.modules.governance.admin.mapper.schema import AdminSchemaMapper
from app.modules.llm.replacement import announce_retirement

router = APIRouter(prefix="/admin/models", tags=["model administration"])


@router.put("/{model_id}/retirement", status_code=204)
async def announce(
    model_id: UUID, body: schemas.RetirementRequest, session: Session, owner: Owner
):
    value = AdminSchemaMapper.to_retirement(body)
    with errors():
        await announce_retirement(
            session,
            actor_id=owner,
            model_id=model_id,
            announced_at=value.announced_at,
            shutdown_at=value.shutdown_at,
        )
