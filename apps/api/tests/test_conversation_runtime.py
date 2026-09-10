from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.command import context
from app.modules.content.lorebook import repository as LorebookRepository
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as ProductTypes
from app.modules.llm.types import ExecutionView
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [None, "dragon", "castle"])
async def test_runtime_activates_published_snapshot_without_live_lorebook_reads(
    monkeypatch, text
):
    cid, owner, pid, sid, start_id, book_id = [uuid4() for _ in range(6)]
    conversation = ConversationTypes.ConversationInfo(
        cid, owner, pid, sid, sid, start_id, datetime.now(UTC)
    )
    always = {
        "id": "always",
        "content": "Published world",
        "activation_type": "always",
        "entry_type": "world",
        "is_enabled": True,
    }
    keyword = {
        **always,
        "id": "keyword",
        "activation_type": "keyword",
        "key_triggers": ["dragon"],
        "match_mode": "contains",
    }
    lorebook = LorebookTypes.LorebookSnapshotInfo(
        book_id, uuid4(), 1, {"entries": [always, keyword]}
    )
    snapshot = ProductTypes.ProductSnapshotInfo(sid, pid, 1, {}, None, None)
    runtime = ProductTypes.SnapshotRuntimeView(
        ProductTypes.SnapshotCompositionInfo(
            characters=[],
            books=[
                ProductTypes.SnapshotLorebookInfo(
                    uuid4(), book_id, "main", 0, True, "all"
                )
            ],
            targets=[],
            starts=[
                ProductTypes.SnapshotStartInfo(
                    start_id, uuid4(), "Start", "Published opening", 0
                )
            ],
        ),
        characters={},
        lorebooks={book_id: lorebook},
    )
    get_owned = AsyncMock(return_value=conversation)
    get_snapshot = AsyncMock(return_value=snapshot)
    get_runtime = AsyncMock(return_value=runtime)
    execution = ExecutionView(uuid4(), "provider", "model", "low", False, None)
    monkeypatch.setattr(context, "get_owned_conversation", get_owned)
    monkeypatch.setattr(
        context.ProductQueryService, "ensure_snapshot_available", get_snapshot
    )
    monkeypatch.setattr(
        context.ProductViewsService, "get_snapshot_runtime", get_runtime
    )
    monkeypatch.setattr(context, "resolve_execution", AsyncMock(return_value=execution))
    live_lookup = AsyncMock(side_effect=AssertionError("Must not read live entries"))
    monkeypatch.setattr(
        LorebookRepository, "list_enabled_entries_by_activation_type", live_lookup
    )
    args = {} if text is None else {"activation_text": text}
    async with AsyncSession() as session:
        result = await context.prepare_runtime_context(
            session,
            ConversationTypes.PrepareRuntimeContextCommand(
                conversation_id=cid, user_id=owner, **args
            ),
        )
        get_owned.assert_awaited_once_with(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=cid, user_id=owner
            ),
        )
        get_snapshot.assert_awaited_once_with(
            session, ProductTypes.ProductSnapshotCommand(sid)
        )
        get_runtime.assert_awaited_once_with(
            session, ProductTypes.ProductSnapshotCommand(sid)
        )
    assert result.execution == execution
    assert result.product_snapshot_id == str(sid)
    assert result.start.content == "Published opening"
    assert result.lorebooks[0].entries == (
        [always, keyword] if text == "dragon" else [always]
    )
    live_lookup.assert_not_awaited()
    result.lorebooks[0].entries[0]["content"] = "Changed by consumer"
    assert lorebook.snapshot_data["entries"][0]["content"] == "Published world"
