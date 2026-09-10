from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.http.dependencies import Owner, Session, errors
from app.modules.chatting.chat import schemas as Schemas
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import schema as SchemaMapper
from app.modules.chatting.chat.service.command import messages as MessagesCommandService
from app.modules.chatting.chat.service.query import messages as MessagesQueryService

router = APIRouter(
    prefix="/conversations/{conversation_id}/messages", tags=["messages"]
)


@contextmanager
def _message_errors():
    with errors():
        try:
            yield
        except Types.MessageConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Types.MessagePermissionError as exc:
            raise HTTPException(403, str(exc)) from exc


@router.post("", status_code=201, response_model=Schemas.MessageResponseDto)
async def create_message(
    conversation_id: UUID,
    body: Schemas.CreateMessageRequestDto,
    session: Session,
    owner: Owner,
):
    with _message_errors():
        command = SchemaMapper.create_message_request_to_command(
            body, conversation_id, owner
        )
        return SchemaMapper.message_info_to_response(
            await MessagesCommandService.create_message(session, command)
        )


@router.get("", response_model=Schemas.MessagePageResponseDto)
async def list_messages(
    conversation_id: UUID,
    session: Session,
    owner: Owner,
    cursor: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
):
    with _message_errors():
        command = SchemaMapper.list_messages_request_to_command(
            conversation_id, owner, cursor, limit
        )
        return SchemaMapper.message_page_info_to_response(
            await MessagesQueryService.list_messages(session, command)
        )


@router.put("/{message_id}", response_model=Schemas.MessageResponseDto)
async def replace_message(
    conversation_id: UUID,
    message_id: UUID,
    body: Schemas.ReplaceMessageRequestDto,
    session: Session,
    owner: Owner,
):
    with _message_errors():
        command = SchemaMapper.replace_message_request_to_command(
            body, conversation_id, message_id, owner
        )
        return SchemaMapper.message_info_to_response(
            await MessagesCommandService.replace_message(session, command)
        )


@router.delete("/{message_id}", response_model=Schemas.RewindMessagesResponseDto)
async def rewind_messages(
    conversation_id: UUID, message_id: UUID, session: Session, owner: Owner
):
    with _message_errors():
        command = SchemaMapper.rewind_messages_request_to_command(
            conversation_id, message_id, owner
        )
        return SchemaMapper.rewind_messages_info_to_response(
            await MessagesCommandService.rewind_messages(session, command)
        )
