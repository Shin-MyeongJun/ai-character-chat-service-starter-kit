"""Invalidate all derived history and advance the destructive-edit revision."""

from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import advance_history_revision
from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types


async def invalidate_conversation_memories(
    session, command: Types.InvalidateConversationMemoriesCommand
) -> None:
    async with use_case_transaction(session):
        await advance_history_revision(
            session,
            ConversationTypes.AdvanceHistoryRevisionCommand(
                conversation_id=command.conversation_id, user_id=command.owner_id
            ),
        )
        await Repository.delete_conversation_memories(session, command.conversation_id)
        await Repository.delete_memory_job(session, command.conversation_id)
