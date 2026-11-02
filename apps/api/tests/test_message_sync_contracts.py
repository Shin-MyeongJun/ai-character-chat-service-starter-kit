"""Additive message checkpoints; offline query/mapper/HTTP contracts."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_chat_message_contracts import message

from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper.schema import messages as SchemaMapper
from app.modules.chatting.chat.service.query import messages as QueryService
from app.modules.chatting.conversation import types as ConversationTypes


@pytest.mark.asyncio
@pytest.mark.parametrize("after", [None, 10])
@pytest.mark.parametrize("count", [0, 1, 3])
async def test_checkpoint_survives_terminal_and_empty_pages_without_skipping_lookahead(
    monkeypatch: pytest.MonkeyPatch, after: int | None, count: int
) -> None:
    conversation_id, owner_id = uuid4(), uuid4()
    conversation = ConversationTypes.ConversationInfo(
        id=conversation_id,
        user_id=owner_id,
        product_id=uuid4(),
        product_snapshot_id=None,
        initial_snapshot_id=None,
        start_set_id=None,
        created_at=datetime.now(UTC),
        history_revision=7,
    )
    owned = AsyncMock(return_value=conversation)
    rows = [
        message(conversation_id, position=(after or 0) + index + 1)
        for index in range(count)
    ]
    stored = AsyncMock(return_value=rows)
    monkeypatch.setattr(QueryService, "get_owned_conversation", owned)
    monkeypatch.setattr(QueryService.Repository, "list_messages", stored)
    cursor = Types.MessageCursor(conversation_id, after) if after else None
    async with AsyncSession() as session:
        page = await QueryService.list_messages(
            session,
            Types.ListMessagesCommand(
                conversation_id=conversation_id,
                user_id=owner_id,
                cursor=cursor,
                limit=2,
            ),
        )
        stored.assert_awaited_once_with(session, conversation_id, after or 0, 2)
        owned.assert_awaited_once_with(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=conversation_id, user_id=owner_id
            ),
        )
    assert page.history_revision == 7
    assert len(page.items) == min(count, 2)
    expected_position = (after or 0) + min(count, 2) if count else after
    assert page.sync_cursor == (
        Types.MessageCursor(conversation_id, expected_position)
        if expected_position
        else None
    )
    assert page.next_cursor == (page.sync_cursor if count > 2 else None)
    response = SchemaMapper.message_page_info_to_response(page)
    assert response.history_revision == 7
    assert response.sync_cursor == (
        f"v1:{conversation_id}:{expected_position}" if expected_position else None
    )
    if response.sync_cursor:
        following = SchemaMapper.list_messages_request_to_command(
            conversation_id, owner_id, response.sync_cursor, 2
        )
        assert following.cursor == page.sync_cursor


@pytest.mark.asyncio
async def test_missing_ownership_never_returns_messages_or_history_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = AsyncMock(side_effect=LookupError("Conversation not found."))
    stored = AsyncMock()
    monkeypatch.setattr(QueryService, "get_owned_conversation", owned)
    monkeypatch.setattr(QueryService.Repository, "list_messages", stored)
    async with AsyncSession() as session:
        with pytest.raises(LookupError, match="Conversation not found"):
            await QueryService.list_messages(
                session,
                Types.ListMessagesCommand(conversation_id=uuid4(), user_id=uuid4()),
            )
    stored.assert_not_awaited()


def test_legacy_message_page_constructor_keeps_nullable_metadata_defaults() -> None:
    response = SchemaMapper.message_page_info_to_response(
        Types.MessagePageInfo((), None)
    )
    assert response.model_dump() == {
        "items": [],
        "next_cursor": None,
        "history_revision": None,
        "sync_cursor": None,
    }
