"""Owner-scoped activity directory, using the explicit read-projection exception."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import query as ConversationQueryService


async def list_recent_conversations(
    session: AsyncSession, command: Types.ListRecentConversationsCommand
) -> Types.RecentConversationsPageView:
    if (
        not 1 <= command.limit <= 100
        or ((command.cursor_activity_at is None) != (command.cursor_id is None))
        or (
            command.cursor_activity_at is not None
            and command.cursor_activity_at.utcoffset() is None
        )
    ):
        raise ValueError("Invalid activity cursor or limit.")
    total = await ConversationQueryService.count_owned_conversations(
        session,
        ConversationTypes.ListOwnedConversationsCommand(user_id=command.user_id),
    )
    rows = await Repository.list_recent_conversations(
        session,
        command.user_id,
        limit=command.limit,
        cursor_activity_at=command.cursor_activity_at,
        cursor_id=command.cursor_id,
    )
    return PersistenceMapper.recent_conversation_rows_to_page_view(
        rows, command.limit, total
    )
