from uuid import UUID
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from app.modules.content.product.router import Session, Owner, errors
from app.modules.chatting.conversation.service import start_conversation

router=APIRouter(prefix='/conversations',tags=['conversations'])


class StartRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id: UUID
    start_set_id: UUID | None = None


@router.post('',status_code=201)
async def start(body:StartRequest,session:Session,owner:Owner):
    with errors():
        return await start_conversation(session,product_id=body.product_id,user_id=owner,start_set_id=body.start_set_id)
