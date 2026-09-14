from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation.service.query import get_owned_conversation


async def advance_history_revision(
    session, command: Types.AdvanceHistoryRevisionCommand
) -> Types.ConversationInfo:
    async with use_case_transaction(session):
        await get_owned_conversation(
            session,
            Types.OwnedConversationCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                lock=True,
            ),
        )
        row = await Repository.advance_history_revision(
            session, command.conversation_id
        )
        info = PersistenceMapper.conversation_entity_to_info(row)
        assert info is not None
        return info
