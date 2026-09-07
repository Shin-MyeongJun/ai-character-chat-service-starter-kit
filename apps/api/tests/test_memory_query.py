from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from app.db.models.chat import Conversation
from app.db.models.memory import ConversationMemory
from app.modules.memory import repository, types
from app.modules.memory.service import query
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

pytestmark = pytest.mark.asyncio


def uid(value):
    return UUID(int=(0xA << 124) + value)


class AsyncAdapter:
    def __init__(self, session):
        self.session = session

    async def scalars(self, stmt):
        return self.session.scalars(stmt)

    async def scalar(self, stmt):
        return self.session.scalar(stmt)


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(CreateTable(Conversation.__table__))
        connection.execute(CreateTable(ConversationMemory.__table__))
    with Session(engine) as session:
        now = datetime(2026, 9, 7, tzinfo=UTC)
        for cid, owner in [(10, 1), (20, 2), (30, 1)]:
            session.add(
                Conversation(
                    id=uid(cid),
                    user_id=uid(owner),
                    product_id=uid(99),
                    created_at=now,
                    updated_at=now,
                )
            )
        for mid, cid, kind in [
            (101, 10, "summary"),
            (102, 10, "fact"),
            (103, 10, "summary"),
            (104, 20, "fact"),
            (105, 30, "fact"),
        ]:
            session.add(
                ConversationMemory(
                    id=uid(mid),
                    conversation_id=uid(cid),
                    memory_type=kind,
                    content=str(mid),
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
        yield AsyncAdapter(session)
    engine.dispose()


async def test_pages_preserve_scope_and_timestamp_ties(database):
    cursor = None
    seen = []
    for _ in range(4):
        page = await query.list_memories(
            database,
            conversation_id=uid(10),
            owner_id=uid(1),
            limit=1,
            cursor=cursor,
        )
        assert all(isinstance(item, types.MemoryInfo) for item in page.items)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert seen == [uid(103), uid(102), uid(101)]


async def test_owner_and_conversation_isolation(database):
    for cid, owner, mid in [(10, 2, 101), (20, 1, 104), (30, 1, 101)]:
        assert (
            await query.get_memory(
                database,
                memory_id=uid(mid),
                conversation_id=uid(cid),
                owner_id=uid(owner),
            )
            is None
        )
    assert (
        await query.list_memories(
            database,
            conversation_id=uid(10),
            owner_id=uid(2),
        )
    ).items == []
    assert (
        await query.get_latest_summary(
            database,
            conversation_id=uid(10),
            owner_id=uid(2),
        )
        is None
    )
    assert not await repository.conversation_is_owned(
        database,
        conversation_id=uid(10),
        owner_id=uid(2),
    )


async def test_summary_and_type_filters_work_without_embeddings(database):
    summary = await query.get_latest_summary(
        database,
        conversation_id=uid(10),
        owner_id=uid(1),
    )
    assert summary.id == uid(103)
    page = await query.list_memories(
        database,
        conversation_id=uid(10),
        owner_id=uid(1),
        memory_types=("fact",),
    )
    assert [item.id for item in page.items] == [uid(102)]
    assert (
        await query.list_memories(
            database,
            conversation_id=uid(10),
            owner_id=uid(1),
            memory_types=(),
        )
    ).items == []


async def test_unauthorized_search_does_not_embed(database):
    embed = AsyncMock()
    assert (
        await query.search_memories(
            database,
            types.MemorySearchQuery(uid(10), "coffee", uid(2)),
            embed_query=embed,
        )
        == []
    )
    embed.assert_not_awaited()


async def test_search_mapping_and_provider_failure(database, monkeypatch):
    entity = await repository.get_memory(
        database,
        memory_id=uid(102),
        conversation_id=uid(10),
        owner_id=uid(1),
    )
    search = AsyncMock(return_value=[(entity, -0.25)])
    monkeypatch.setattr(repository, "search_memories", search)
    embed = AsyncMock(return_value=[1.0] * 1536)
    request = types.MemorySearchQuery(uid(10), "coffee", uid(1), memory_types=("fact",))
    result = await query.search_memories(database, request, embed_query=embed)
    assert result[0].similarity_score == -0.25
    assert result[0].memory_id == uid(102)
    assert search.await_args.kwargs["owner_id"] == uid(1)
    assert search.await_args.kwargs["memory_types"] == ("fact",)
    search.reset_mock()
    embed.side_effect = RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await query.search_memories(database, request, embed_query=embed)
    search.assert_not_awaited()


@pytest.mark.parametrize(
    "vector", [[1.0], [0.0] * 1536, [float("nan")] * 1536, [float("inf")] * 1536]
)
async def test_invalid_vectors_fail_before_database(vector):
    session = SimpleNamespace(execute=AsyncMock())
    with pytest.raises(ValueError):
        await repository.search_memories(
            session,
            conversation_id=uid(10),
            owner_id=uid(1),
            query_embedding=vector,
        )
    session.execute.assert_not_awaited()


async def test_search_sql_scope_and_distance_conversion():
    entity = object()
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(all=lambda: [(entity, 0.2)]),
        )
    )
    result = await repository.search_memories(
        session,
        conversation_id=uid(10),
        owner_id=uid(1),
        query_embedding=[1.0] * 1536,
        memory_types=("fact",),
        top_k=3,
    )
    assert result == [(entity, 0.8)]
    compiled = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "conversations.user_id =" in sql
    assert "conversation_memories.conversation_id =" in sql
    assert "embedding IS NOT NULL" in sql
    assert "<=>" in sql
    assert uid(10) in compiled.params.values()
    assert uid(1) in compiled.params.values()
    assert ["fact"] in compiled.params.values()


@pytest.mark.parametrize(
    "text,top_k,kinds",
    [(" ", 5, None), ("x", 0, None), ("x", 101, None), ("x", 5, ("manual",))],
)
async def test_invalid_search_request_skips_provider(text, top_k, kinds):
    embed = AsyncMock()
    with pytest.raises(ValueError):
        await query.search_memories(
            object(),
            types.MemorySearchQuery(uid(10), text, uid(1), top_k, kinds),
            embed_query=embed,
        )
    embed.assert_not_awaited()


async def test_empty_type_filter_skips_provider():
    embed = AsyncMock()
    assert (
        await query.search_memories(
            object(),
            types.MemorySearchQuery(uid(10), "x", uid(1), memory_types=()),
            embed_query=embed,
        )
        == []
    )
    embed.assert_not_awaited()


async def test_repository_writes_leave_transaction_to_caller():
    session = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
        delete=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    entity = ConversationMemory(
        conversation_id=uid(10), memory_type="fact", content="x"
    )
    assert await repository.create_memory(session, entity) is entity
    assert await repository.update_memory(session, entity) is entity
    await repository.delete_memory(session, entity)
    assert session.flush.await_count == 3
    session.delete.assert_awaited_once_with(entity)
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
