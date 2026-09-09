from uuid import UUID

from fastapi import APIRouter

from app.modules.chatting.conversation import schemas
from app.modules.chatting.conversation.mapper.schema import ConversationSchemaMapper
from app.modules.chatting.conversation.service import start_conversation
from app.modules.content.product import schemas as product_schemas
from app.modules.content.product.http import Owner, Session, errors
from app.modules.content.product.mapper.schema import ProductSchemaMapper

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=201, response_model=schemas.ConversationStartedResponseDto)
async def start(body: schemas.StartRequest, session: Session, owner: Owner):
    value = ConversationSchemaMapper.to_start(body)
    with errors():
        return ConversationSchemaMapper.started_response(
            await start_conversation(
                session,
                product_id=value.product_id,
                user_id=owner,
                start_set_id=value.start_set_id,
            )
        )


@router.get(
    "/{conversation_id}/updates",
    response_model=product_schemas.PendingUpdatesInfoResponseDto,
)
async def updates(conversation_id: UUID, session: Session, owner: Owner):
    from app.modules.content.product.service.notices import pending_updates

    with errors():
        return ProductSchemaMapper.updates_response(
            await pending_updates(
                session, conversation_id=conversation_id, user_id=owner
            )
        )


@router.post(
    "/{conversation_id}/version", response_model=schemas.VersionSwitchedResponseDto
)
async def switch(
    conversation_id: UUID, body: schemas.SwitchRequest, session: Session, owner: Owner
):
    value = ConversationSchemaMapper.to_switch(body)
    from app.modules.chatting.conversation.versions import switch_version

    with errors():
        return ConversationSchemaMapper.switched_response(
            await switch_version(
                session,
                conversation_id=conversation_id,
                user_id=owner,
                target_snapshot_id=value.target_snapshot_id,
            )
        )
