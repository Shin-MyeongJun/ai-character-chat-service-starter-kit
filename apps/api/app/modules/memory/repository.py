"""Memory persistence. The caller owns the transaction and authorizes writes."""

from collections.abc import Sequence
from math import isfinite
from typing import get_args
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Conversation
from app.db.models.memory import ConversationMemory
from app.modules.memory import types

DEFAULT_MEMORY_LIST_LIMIT = 50
MAX_MEMORY_LIST_LIMIT = 100
MAX_MEMORY_SEARCH_LIMIT = 100


def _scoped_select(
    conversation_id: UUID,
    owner_id: UUID,
) -> Select[tuple[ConversationMemory]]:
    return (
        select(ConversationMemory)
        .join(
            Conversation,
            Conversation.id == ConversationMemory.conversation_id,
        )
        .where(
            ConversationMemory.conversation_id == conversation_id,
            Conversation.user_id == owner_id,
        )
    )


def validate_memory_types(memory_types: Sequence[types.MemoryType] | None) -> None:
    if memory_types is not None and any(
        item not in get_args(types.MemoryType) for item in memory_types
    ):
        raise ValueError("Invalid memory type.")


async def conversation_is_owned(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
) -> bool:
    result = await session.scalar(
        select(Conversation.id).where(
            Conversation.id == conversation_id,
            Conversation.user_id == owner_id,
        )
    )
    return result is not None


async def create_memory(
    session: AsyncSession,
    memory: ConversationMemory,
) -> ConversationMemory:
    session.add(memory)
    await session.flush()
    await session.refresh(memory)
    return memory


async def update_memory(
    session: AsyncSession,
    memory: ConversationMemory,
) -> ConversationMemory:
    session.add(memory)
    await session.flush()
    await session.refresh(memory)
    return memory


async def delete_memory(session: AsyncSession, memory: ConversationMemory) -> None:
    await session.delete(memory)
    await session.flush()


async def get_memory(
    session: AsyncSession,
    *,
    memory_id: UUID,
    conversation_id: UUID,
    owner_id: UUID,
    for_update: bool = False,
) -> ConversationMemory | None:
    stmt = _scoped_select(conversation_id, owner_id).where(
        ConversationMemory.id == memory_id,
    )
    if for_update:
        stmt = stmt.with_for_update(of=ConversationMemory)
    return (await session.scalars(stmt)).one_or_none()


async def list_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    cursor: types.MemoryCursor | None = None,
    limit: int = DEFAULT_MEMORY_LIST_LIMIT,
    memory_types: Sequence[types.MemoryType] | None = None,
) -> types.MemoryPage[ConversationMemory]:
    """Newest first; None selects all types and an empty sequence selects none."""
    validate_memory_types(memory_types)
    limit = min(max(limit, 1), MAX_MEMORY_LIST_LIMIT)
    stmt = _scoped_select(conversation_id, owner_id)
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    if cursor is not None:
        stmt = stmt.where(
            or_(
                ConversationMemory.created_at < cursor.created_at,
                and_(
                    ConversationMemory.created_at == cursor.created_at,
                    ConversationMemory.id < cursor.id,
                ),
            )
        )
    stmt = stmt.order_by(
        ConversationMemory.created_at.desc(),
        ConversationMemory.id.desc(),
    ).limit(limit + 1)
    rows = list((await session.scalars(stmt)).all())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = types.MemoryCursor(created_at=last.created_at, id=last.id)
    return types.MemoryPage(items=items, next_cursor=next_cursor)


async def get_latest_summary(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
) -> ConversationMemory | None:
    """Latest by creation time, independent of whether it has an embedding."""
    page = await list_memories(
        session,
        conversation_id=conversation_id,
        owner_id=owner_id,
        memory_types=("summary",),
        limit=1,
    )
    return page.items[0] if page.items else None


async def search_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    query_embedding: Sequence[float],
    top_k: int = 5,
    memory_types: Sequence[types.MemoryType] | None = None,
) -> list[tuple[ConversationMemory, float]]:
    """Return cosine similarities. Existing indexes determine exact/ANN execution.

    Caller must use the same model as stored memories; the schema does not yet
    track model versions. No threshold or reranking policy is applied.
    """
    validate_memory_types(memory_types)
    if not 1 <= top_k <= MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(f"top_k must be between 1 and {MAX_MEMORY_SEARCH_LIMIT}.")
    vector = list(query_embedding)
    dimension = ConversationMemory.__table__.c.embedding.type.dim
    if len(vector) != dimension or not all(isfinite(value) for value in vector):
        raise ValueError(f"Query embedding must contain {dimension} finite values.")
    if not any(vector):
        raise ValueError("Cosine search requires a nonzero query embedding.")
    distance = ConversationMemory.embedding.cosine_distance(vector)
    stmt = (
        _scoped_select(conversation_id, owner_id)
        .add_columns(
            distance.label("distance"),
        )
        .where(ConversationMemory.embedding.is_not(None))
    )
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    rows = (await session.execute(stmt.order_by(distance).limit(top_k))).all()
    return [
        (entity, 1.0 - float(value))
        for entity, value in rows
        if value is not None and isfinite(value)
    ]
