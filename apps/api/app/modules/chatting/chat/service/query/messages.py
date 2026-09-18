# 소유 대화의 현재 선형 이력을 조회한다. 페이지 사이 편집까지 고정한 스냅샷 조회는 아니다.
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import get_owned_conversation


async def list_messages(
    session, command: Types.ListMessagesCommand
) -> Types.MessagePageInfo:
    if type(command.limit) is not int or not 1 <= command.limit <= 100:
        raise ValueError("Page limit must be 1–100.")
    if command.cursor and (
        command.cursor.conversation_id != command.conversation_id
        or type(command.cursor.position) is not int
        or not 0 < command.cursor.position < 2**63
    ):
        raise ValueError("Invalid message cursor.")
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    rows = await Repository.list_messages(
        session,
        command.conversation_id,
        command.cursor.position if command.cursor else 0,
        command.limit,
    )
    return PersistenceMapper.messages_entities_to_page_info(
        rows, command.conversation_id, command.limit
    )


async def list_memory_source(
    session, command: Types.ListMemorySourceCommand
) -> Types.MemorySourceInfo:
    if (
        type(command.after_position) is not int
        or command.after_position < 0
        or command.through_position is not None
        and (
            type(command.through_position) is not int
            or command.through_position <= command.after_position
        )
        or type(command.limit) is not int
        or not 1 <= command.limit <= 10000
    ):
        raise ValueError("Invalid internal memory source range.")
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    rows = await Repository.list_message_range(
        session,
        command.conversation_id,
        command.after_position,
        command.through_position,
        command.limit,
    )
    return PersistenceMapper.messages_entities_to_memory_source_info(
        rows, command.limit
    )
