from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.modules.content.product.router import Owner, Session, errors
from app.modules.llm.replacement import announce_retirement

router = APIRouter(prefix="/admin/models", tags=["model administration"])


class RetirementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    announced_at: datetime
    shutdown_at: datetime


@router.put("/{model_id}/retirement", status_code=204)
async def announce(
    model_id: UUID, body: RetirementRequest, session: Session, owner: Owner
):
    with errors():
        await announce_retirement(
            session,
            actor_id=owner,
            model_id=model_id,
            announced_at=body.announced_at,
            shutdown_at=body.shutdown_at,
        )
