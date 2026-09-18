# 관리자의 종료 공지 요청을 llm.announce_retirement에 전달한다. 날짜·DB 관리자 검사는 llm 서비스가 수행한다.
from uuid import UUID

from fastapi import APIRouter

from app.http.dependencies import Owner, Session, errors
from app.modules.governance.admin import schemas as Schemas
from app.modules.governance.admin.mapper.schema import AdminSchemaMapper as SchemaMapper
from app.modules.llm import types as LlmTypes
from app.modules.llm.service.replacement import announce_retirement

router = APIRouter(prefix="/admin/models", tags=["model administration"])


@router.put("/{model_id}/retirement", status_code=204)
async def announce(
    model_id: UUID, body: Schemas.RetirementRequest, session: Session, owner: Owner
):
    value = SchemaMapper.retirement_request_to_command(body)
    with errors():
        await announce_retirement(
            session,
            LlmTypes.AnnounceRetirementCommand(
                actor_id=owner,
                model_id=model_id,
                announced_at=value.announced_at,
                shutdown_at=value.shutdown_at,
            ),
        )
