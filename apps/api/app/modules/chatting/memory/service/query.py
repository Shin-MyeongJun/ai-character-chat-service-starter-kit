"""Owner-scoped reads; no commit/rollback and no embedding provider selection.

Pass owner_id from trusted authentication context. Missing and inaccessible
records return None for singular reads and empty results for collections.
"""

from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from app.modules.chatting.memory import repository, types
from app.modules.chatting.memory.mapper import persistence
from sqlalchemy.ext.asyncio import AsyncSession

EmbedQuery = Callable[[str], Awaitable[Sequence[float]]]


async def get_memory(
    session: AsyncSession,
    *,
    memory_id: UUID,
    conversation_id: UUID,
    owner_id: UUID,
) -> types.MemoryInfo | None:
    entity = await repository.get_memory(
        session,
        memory_id=memory_id,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )
    return persistence.memory_entity_to_info(entity) if entity is not None else None


async def list_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    cursor: types.MemoryCursor | None = None,
    limit: int = repository.DEFAULT_MEMORY_LIST_LIMIT,
    memory_types: Sequence[types.MemoryType] | None = None,
) -> types.MemoryPage[types.MemoryInfo]:
    page = await repository.list_memories(
        session,
        conversation_id=conversation_id,
        owner_id=owner_id,
        cursor=cursor,
        limit=limit,
        memory_types=memory_types,
    )
    return types.MemoryPage(
        items=[persistence.memory_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


async def get_latest_summary(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
) -> types.MemoryInfo | None:
    entity = await repository.get_latest_summary(
        session,
        conversation_id=conversation_id,
        owner_id=owner_id,
    )
    return persistence.memory_entity_to_info(entity) if entity is not None else None


async def search_memories(
    session: AsyncSession,
    query: types.MemorySearchQuery,
    *,
    embed_query: EmbedQuery,
) -> list[types.RetrievedMemory]:
    """Embed after authorization; provider failures propagate instead of looking empty.

    Caller supplies context-enriched query_text and a model-compatible embedder.
    Extraction, query rewriting, thresholds and reranking remain deferred.
    """
    if not query.query_text.strip():
        raise ValueError("Memory search text must not be blank.")
    if not 1 <= query.top_k <= repository.MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(
            f"top_k must be between 1 and {repository.MAX_MEMORY_SEARCH_LIMIT}."
        )
    repository.validate_memory_types(query.memory_types)
    if query.memory_types == ():
        return []
    if not await repository.conversation_is_owned(
        session,
        conversation_id=query.conversation_id,
        owner_id=query.owner_id,
    ):
        return []
    vector = await embed_query(query.query_text)
    rows = await repository.search_memories(
        session,
        conversation_id=query.conversation_id,
        owner_id=query.owner_id,
        query_embedding=vector,
        top_k=query.top_k,
        memory_types=query.memory_types,
    )
    return [
        persistence.memory_entity_to_retrieved(entity, similarity_score=score)
        for entity, score in rows
    ]
