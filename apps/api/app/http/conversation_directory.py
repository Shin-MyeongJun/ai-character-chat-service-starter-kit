"""Owner's cross-module conversation directory HTTP boundary."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.http.dependencies import Owner, Session, errors
from app.modules.chatting.conversation import schemas as Schemas
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper.schema import ConversationSchemaMapper
from app.use_cases.conversation_directory import list_recent_conversations

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/mine", response_model=Schemas.ConversationListPageResponseDto)
async def list_mine(
    session: Session, owner: Owner,
    limit: int = Query(default=30, ge=1, le=100),
    cursor_created_at: str | None = None,
    cursor_id: UUID | None = None,
):
    with errors():
        created_at = datetime.fromisoformat(cursor_created_at) if cursor_created_at else None
        return ConversationSchemaMapper.conversation_list_page_to_response(
            await list_recent_conversations(
                session, Types.ListOwnedConversationsCommand(owner, limit, created_at, cursor_id)
            )
        )
