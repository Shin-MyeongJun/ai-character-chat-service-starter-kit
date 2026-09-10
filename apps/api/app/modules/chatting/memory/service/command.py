"""Invalidate derived history; provenance does not describe complete dependencies."""

from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types


async def invalidate_conversation_memories(
    session, command: Types.InvalidateConversationMemoriesCommand
) -> None:
    async with use_case_transaction(session):
        await get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=command.conversation_id,
                user_id=command.owner_id,
                lock=True,
            ),
        )
        await Repository.delete_conversation_memories(session, command.conversation_id)
