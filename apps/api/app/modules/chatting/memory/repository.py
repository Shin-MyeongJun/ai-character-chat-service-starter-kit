"""Memory persistence. The caller owns the transaction and authorizes writes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
from typing import cast, get_args
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Conversation
from app.db.models.memory import ConversationMemory
from app.db.pagination import fetch_cursor_page
from app.modules.chatting.memory import types as Types

DEFAULT_MEMORY_LIST_LIMIT = 50
MAX_MEMORY_LIST_LIMIT = 100
MAX_MEMORY_SEARCH_LIMIT = 100
MEMORY_EMBEDDING_DIMENSION = cast(
    Vector, ConversationMemory.__table__.c.embedding.type
).dim


async def delete_conversation_memories(session, conversation_id) -> None:
    await session.execute(
        delete(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id
        )
    )


@dataclass(frozen=True)
class MemoryPageRow:
    items: list[ConversationMemory]
    next_cursor: Types.MemoryCursor | None


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


def validate_memory_types(memory_types: Sequence[Types.MemoryType] | None) -> None:
    if memory_types is not None and any(
        item not in get_args(Types.MemoryType) for item in memory_types
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
    cursor: Types.MemoryCursor | None = None,
    limit: int = DEFAULT_MEMORY_LIST_LIMIT,
    memory_types: Sequence[Types.MemoryType] | None = None,
) -> MemoryPageRow:
    """Newest first; None selects all types and an empty sequence selects none."""
    validate_memory_types(memory_types)
    stmt = _scoped_select(conversation_id, owner_id)
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    return await fetch_cursor_page(
        session,
        stmt,
        created_at=ConversationMemory.created_at,
        id_column=ConversationMemory.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_MEMORY_LIST_LIMIT,
        cursor_factory=Types.MemoryCursor,
        page_factory=MemoryPageRow,
    )


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
    embedding_provider: str,
    embedding_model: str,
    top_k: int = 5,
    memory_types: Sequence[Types.MemoryType] | None = None,
) -> list[tuple[ConversationMemory, float]]:
    """Return cosine similarities. Existing indexes determine exact/ANN execution.

    Only rows with exact provider/model metadata are compatible. Legacy rows with
    unknown metadata are deliberately excluded. No reranking policy is applied.
    """
    validate_memory_types(memory_types)
    if not 1 <= top_k <= MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(f"top_k must be between 1 and {MAX_MEMORY_SEARCH_LIMIT}.")
    if not isinstance(embedding_provider, str) or not embedding_provider.strip():
        raise ValueError("embedding_provider must be a non-blank string.")
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("embedding_model must be a non-blank string.")
    vector = list(query_embedding)
    if len(vector) != MEMORY_EMBEDDING_DIMENSION or not all(
        isfinite(value) for value in vector
    ):
        raise ValueError(
            f"Query embedding must contain {MEMORY_EMBEDDING_DIMENSION} finite values."
        )
    if not any(vector):
        raise ValueError("Cosine search requires a nonzero query embedding.")
    distance = ConversationMemory.embedding.cosine_distance(vector)
    stmt = (
        _scoped_select(conversation_id, owner_id)
        .add_columns(
            distance.label("distance"),
        )
        .where(
            ConversationMemory.embedding.is_not(None),
            ConversationMemory.embedding_provider == embedding_provider,
            ConversationMemory.embedding_model == embedding_model,
        )
    )
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    rows = (await session.execute(stmt.order_by(distance).limit(top_k))).all()
    return [
        (entity, 1.0 - float(value))
        for entity, value in rows
        if value is not None and isfinite(value)
    ]
