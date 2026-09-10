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
