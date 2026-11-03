"""Owner's activity directory; the public cursor_created_at carries activity time."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.http.dependencies import Owner, Session, errors
from app.http.mapper.conversation_directory import recent_conversations_page_to_response
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service import views as ChatViewsService
from app.modules.chatting.conversation import schemas as Schemas

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/mine", response_model=Schemas.ConversationListPageResponseDto)
async def list_mine(
    session: Session,
    owner: Owner,
    limit: int = Query(default=30, ge=1, le=100),
    cursor_created_at: str | None = None,
    cursor_id: UUID | None = None,
) -> Schemas.ConversationListPageResponseDto:
    with errors():
        created_at = (
            datetime.fromisoformat(cursor_created_at) if cursor_created_at else None
        )
        return recent_conversations_page_to_response(
            await ChatViewsService.list_recent_conversations(
                session,
                ChatTypes.ListRecentConversationsCommand(
                    user_id=owner,
                    limit=limit,
                    cursor_activity_at=created_at,
                    cursor_id=cursor_id,
                ),
            )
        )
