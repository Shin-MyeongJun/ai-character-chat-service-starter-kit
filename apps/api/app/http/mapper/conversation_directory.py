"""Serialize the composed activity page, including previews and owner totals."""

from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.conversation import schemas as Schemas


def recent_conversations_page_to_response(
    view: ChatTypes.RecentConversationsPageView,
) -> Schemas.ConversationListPageResponseDto:
    return Schemas.ConversationListPageResponseDto.model_validate(view)
