"""Serialize the composed activity page, including previews and owner totals."""

from app.modules.chatting.conversation import schemas as Schemas
from app.use_cases.conversation_directory import RecentConversationsPageView


def recent_conversations_page_to_response(
    view: RecentConversationsPageView,
) -> Schemas.ConversationListPageResponseDto:
    return Schemas.ConversationListPageResponseDto.model_validate(view)
