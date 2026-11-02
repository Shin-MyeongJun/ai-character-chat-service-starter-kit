"""Compatibility entry point for the owner's activity-ordered conversation page."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service import views as ChatViewsService
from app.modules.chatting.chat.types import (
    RecentConversationsPageView as RecentConversationsPageView,
)
from app.modules.chatting.chat.types import (
    RecentConversationView as RecentConversationView,
)
from app.modules.chatting.conversation import types as ConversationTypes


async def list_recent_conversations(
    session: AsyncSession, command: ConversationTypes.ListOwnedConversationsCommand
) -> RecentConversationsPageView:
    """Keep the legacy cursor field name; it carries activity time on this API.

    The directory is live rather than a snapshot across requests. A room gaining
    new activity can move before an existing cursor; refresh restarts traversal.
    """
    return await ChatViewsService.list_recent_conversations(
        session,
        ChatTypes.ListRecentConversationsCommand(
            user_id=command.user_id,
            limit=command.limit,
            cursor_activity_at=command.cursor_created_at,
            cursor_id=command.cursor_id,
        ),
    )
