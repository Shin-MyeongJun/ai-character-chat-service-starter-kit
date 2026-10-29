"""Combine an owner's conversation page with chat-owned message previews."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query.messages import list_conversation_activity
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import list_owned_conversations


@dataclass(frozen=True, slots=True)
class RecentConversationView:
    id: UUID
    product_id: UUID
    title: str | None
    created_at: datetime
    last_message: str | None
    last_activity_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RecentConversationsPageView:
    items: tuple[RecentConversationView, ...]
    next_cursor_created_at: datetime | None
    next_cursor_id: UUID | None
    total: int = 0


async def list_recent_conversations(
    session: AsyncSession, command: ConversationTypes.ListOwnedConversationsCommand
) -> RecentConversationsPageView:
    """Merge public conversation/chat reads before activity pagination.

    No cross-domain data JOIN is permitted. Walk owner metadata in bounded batches,
    collect chat activity, then order the complete owner scope. Empty rooms use their
    creation time. This is a live READ COMMITTED view, not a multi-request snapshot:
    newly active rows can move before an old cursor; refresh restarts the traversal.
    """
    if (
        not 1 <= command.limit <= 100
        or ((command.cursor_created_at is None) != (command.cursor_id is None))
        or (
            command.cursor_created_at is not None
            and command.cursor_created_at.utcoffset() is None
        )
    ):
        raise ValueError("Invalid activity cursor or limit.")
    rows: list[RecentConversationView] = []
    scan = ConversationTypes.ListOwnedConversationsCommand(command.user_id, 100)
    while True:
        page = await list_owned_conversations(session, scan)
        activities = await list_conversation_activity(
            session,
            ChatTypes.ListConversationPreviewsCommand(
                command.user_id, tuple(item.id for item in page.items)
            ),
        )
        for item in page.items:
            activity = activities.get(item.id)
            rows.append(
                RecentConversationView(
                    item.id,
                    item.product_id,
                    item.title,
                    item.created_at,
                    activity.content if activity else None,
                    activity.created_at if activity else item.created_at,
                )
            )
        if page.next_cursor_id is None:
            break
        scan = ConversationTypes.ListOwnedConversationsCommand(
            command.user_id, 100, page.next_cursor_created_at, page.next_cursor_id
        )
    total = len(rows)
    rows.sort(key=_activity_key, reverse=True)
    if command.cursor_created_at is not None:
        # The paired cursor was checked above; preserve its existing raw value.
        cursor_id = cast(UUID, command.cursor_id)
        rows = [
            item
            for item in rows
            if _activity_key(item) < (command.cursor_created_at, cursor_id)
        ]
    selected = tuple(rows[: command.limit])
    last = selected[-1] if len(rows) > command.limit else None
    return RecentConversationsPageView(
        items=selected,
        next_cursor_created_at=last.last_activity_at if last else None,
        next_cursor_id=last.id if last else None,
        total=total,
    )


def _activity_key(item: RecentConversationView) -> tuple[datetime, UUID]:
    # Every row above supplies activity.created_at or conversation.created_at.
    # The public dataclass's optional default remains compatible with old callers.
    return cast(datetime, item.last_activity_at), item.id
