from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.modules.chatting.conversation.service import start_conversation
from app.modules.content.product.router import Owner, Session, errors

router = APIRouter(prefix="/conversations", tags=["conversations"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    start_set_id: UUID | None = None


@router.post("", status_code=201)
async def start(body: StartRequest, session: Session, owner: Owner):
    with errors():
        return await start_conversation(
            session,
            product_id=body.product_id,
            user_id=owner,
            start_set_id=body.start_set_id,
        )


@router.get("/{conversation_id}/updates")
async def updates(conversation_id: UUID, session: Session, owner: Owner):
    from app.modules.content.product.service.notices import pending_updates

    with errors():
        return await pending_updates(
            session, conversation_id=conversation_id, user_id=owner
        )


class SwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_snapshot_id: UUID


@router.post("/{conversation_id}/version")
async def switch(
    conversation_id: UUID, body: SwitchRequest, session: Session, owner: Owner
):
    from app.modules.chatting.conversation.versions import switch_version

    with errors():
        return await switch_version(
            session,
            conversation_id=conversation_id,
            user_id=owner,
            target_snapshot_id=body.target_snapshot_id,
        )
