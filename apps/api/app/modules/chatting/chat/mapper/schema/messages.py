# 메시지 커서 v1:conversation_id:position을 변환한다. 대화 일치와 위치 범위 검사는 query 서비스가 한다.
from dataclasses import asdict
from uuid import UUID

from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.schemas import messages as Schemas


def create_message_request_to_command(
    body: Schemas.CreateMessageRequestDto, conversation_id: UUID, user_id: UUID
) -> Types.CreateMessageCommand:
    return Types.CreateMessageCommand(
        conversation_id=conversation_id,
        user_id=user_id,
        request_key=body.request_key,
        content=body.content,
    )


def replace_message_request_to_command(
    body: Schemas.ReplaceMessageRequestDto,
    conversation_id: UUID,
    message_id: UUID,
    user_id: UUID,
) -> Types.ReplaceMessageCommand:
    return Types.ReplaceMessageCommand(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        expected_revision=body.expected_revision,
        content=body.content,
    )


def list_messages_request_to_command(
    conversation_id: UUID, user_id: UUID, cursor: str | None, limit: int
) -> Types.ListMessagesCommand:
    message_cursor = None
    if cursor is not None:
        try:
            version, cursor_conversation_id, position = cursor.split(":")
            if version != "v1" or not position.isascii() or not position.isdecimal():
                raise ValueError
            message_cursor = Types.MessageCursor(
                conversation_id=UUID(cursor_conversation_id), position=int(position)
            )
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid message cursor.") from exc
    return Types.ListMessagesCommand(
        conversation_id=conversation_id,
        user_id=user_id,
        cursor=message_cursor,
        limit=limit,
    )


def rewind_messages_request_to_command(
    conversation_id: UUID, message_id: UUID, user_id: UUID
) -> Types.RewindMessagesCommand:
    return Types.RewindMessagesCommand(
        conversation_id=conversation_id, message_id=message_id, user_id=user_id
    )


def message_info_to_response(info: Types.MessageInfo) -> Schemas.MessageResponseDto:
    return Schemas.MessageResponseDto(**asdict(info))


def message_page_info_to_response(
    info: Types.MessagePageInfo,
) -> Schemas.MessagePageResponseDto:
    cursor = info.next_cursor
    return Schemas.MessagePageResponseDto(
        items=[message_info_to_response(item) for item in info.items],
        next_cursor=f"v1:{cursor.conversation_id}:{cursor.position}"
        if cursor
        else None,
    )


def rewind_messages_info_to_response(
    info: Types.RewindMessagesInfo,
) -> Schemas.RewindMessagesResponseDto:
    return Schemas.RewindMessagesResponseDto(deleted_count=info.deleted_count)
