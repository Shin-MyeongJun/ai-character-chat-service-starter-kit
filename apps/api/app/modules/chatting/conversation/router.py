from uuid import UUID

from fastapi import APIRouter

from app.http.dependencies import Owner, Session, errors
from app.modules.chatting.conversation import schemas as Schemas
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper.schema import (
    ConversationSchemaMapper as SchemaMapper,
)
from app.modules.chatting.conversation.mapper.schema import (
    pending_updates_view_to_response,
)
from app.modules.chatting.conversation.service import start_conversation
from app.modules.content.product import types as ProductTypes

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=201, response_model=Schemas.ConversationStartedResponseDto)
async def start(body: Schemas.StartRequest, session: Session, owner: Owner):
    value = SchemaMapper.conversation_start_request_to_command(body)
    with errors():
        return SchemaMapper.conversation_started_info_to_response(
            await start_conversation(
                session,
                Types.StartConversationCommand(
                    product_id=value.product_id,
                    user_id=owner,
                    start_set_id=value.start_set_id,
                ),
            )
        )


@router.get(
    "/{conversation_id}/updates", response_model=Schemas.PendingUpdatesInfoResponseDto
)
async def updates(conversation_id: UUID, session: Session, owner: Owner):
    from app.modules.content.product.service.views.notices import get_pending_updates

    with errors():
        return pending_updates_view_to_response(
            await get_pending_updates(
                session,
                ProductTypes.PendingUpdatesCommand(
                    conversation_id=conversation_id, user_id=owner
                ),
            )
        )


@router.post(
    "/{conversation_id}/version", response_model=Schemas.VersionSwitchedResponseDto
)
async def switch(
    conversation_id: UUID, body: Schemas.SwitchRequest, session: Session, owner: Owner
):
    value = SchemaMapper.conversation_switch_request_to_command(body)
    from app.modules.chatting.conversation.service.command.versions import (
        switch_version,
    )

    with errors():
        return SchemaMapper.conversation_switched_info_to_response(
            await switch_version(
                session,
                Types.SwitchVersionCommand(
                    conversation_id=conversation_id,
                    user_id=owner,
                    target_snapshot_id=value.target_snapshot_id,
                ),
            )
        )
