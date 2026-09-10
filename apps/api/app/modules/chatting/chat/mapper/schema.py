from dataclasses import asdict
from uuid import UUID

from app.modules.chatting.chat import schemas as Schemas
from app.modules.chatting.chat import types as Types


def create_message_request_to_command(
    body, conversation_id, user_id
) -> Types.CreateMessageCommand:
    return Types.CreateMessageCommand(
        conversation_id=conversation_id,
        user_id=user_id,
        request_key=body.request_key,
        content=body.content,
    )


def replace_message_request_to_command(
    body, conversation_id, message_id, user_id
) -> Types.ReplaceMessageCommand:
    return Types.ReplaceMessageCommand(
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        expected_revision=body.expected_revision,
        content=body.content,
    )


def list_messages_request_to_command(
    conversation_id, user_id, cursor, limit
) -> Types.ListMessagesCommand:
    value = None
    if cursor is not None:
        try:
            version, cid, position = cursor.split(":")
            if version != "v1" or not position.isascii() or not position.isdecimal():
                raise ValueError
            value = Types.MessageCursor(UUID(cid), int(position))
        except (ValueError, AttributeError) as exc:
            raise ValueError("Invalid message cursor.") from exc
    return Types.ListMessagesCommand(
        conversation_id=conversation_id, user_id=user_id, cursor=value, limit=limit
    )


def rewind_messages_request_to_command(
    conversation_id, message_id, user_id
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
