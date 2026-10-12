"""Combine an owner's conversation page with chat-owned message previews."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import list_conversation_previews
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import list_owned_conversations


@dataclass(frozen=True, slots=True)
class RecentConversationView:
    id: UUID
    product_id: UUID
    title: str | None
    created_at: datetime
    last_message: str | None


@dataclass(frozen=True, slots=True)
class RecentConversationsPageView:
    items: tuple[RecentConversationView, ...]
    next_cursor_created_at: datetime | None
    next_cursor_id: UUID | None


async def list_recent_conversations(
    session, command: ConversationTypes.ListOwnedConversationsCommand
) -> RecentConversationsPageView:
    page = await list_owned_conversations(session, command)
    previews = await list_conversation_previews(
        session,
        ChatTypes.ListConversationPreviewsCommand(
            command.user_id, tuple(item.id for item in page.items)
        ),
    )
    return RecentConversationsPageView(
        items=tuple(
            RecentConversationView(
                item.id, item.product_id, item.title, item.created_at,
                previews.get(item.id),
            )
            for item in page.items
        ),
        next_cursor_created_at=page.next_cursor_created_at,
        next_cursor_id=page.next_cursor_id,
    )
