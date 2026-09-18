# 대화 시작은 최상위 use_case, 업데이트 안내는 product View, 실제 버전 전환은 conversation Command에 연결한다.
from uuid import UUID

from fastapi import APIRouter

from app.http.dependencies import Owner, Session, errors
from app.modules.chatting.conversation import schemas as Schemas
from app.modules.chatting.conversation.mapper.schema import (
    ConversationSchemaMapper as SchemaMapper,
)
from app.modules.content.product import types as ProductTypes
from app.use_cases.conversations import start_conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=201, response_model=Schemas.ConversationStartedResponseDto)
async def start(body: Schemas.StartRequest, session: Session, owner: Owner):
    command = SchemaMapper.conversation_start_request_to_command(body, owner)
    with errors():
        return SchemaMapper.conversation_started_info_to_response(
            await start_conversation(session, command)
        )


@router.get(
    "/{conversation_id}/updates", response_model=Schemas.PendingUpdatesInfoResponseDto
)
async def updates(conversation_id: UUID, session: Session, owner: Owner):
    from app.modules.content.product.service.views.notices import get_pending_updates

    with errors():
        return SchemaMapper.pending_updates_view_to_response(
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
    command = SchemaMapper.conversation_switch_request_to_command(
        body, conversation_id, owner
    )
    from app.modules.chatting.conversation.service.command.versions import (
        switch_version,
    )

    with errors():
        return SchemaMapper.conversation_switched_info_to_response(
            await switch_version(session, command)
        )
