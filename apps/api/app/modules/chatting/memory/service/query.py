"""Owner-scoped reads; no commit/rollback and no embedding provider selection.

Pass owner_id from trusted authentication context. Missing and inaccessible
records return None for singular reads and empty results for collections.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper
from app.modules.llm import service as LLMService
from app.modules.llm import types as LLMTypes


async def get_memory(
    session: AsyncSession, command: Types.GetMemoryCommand
) -> Types.MemoryInfo | None:
    memory_id = command.memory_id
    conversation_id = command.conversation_id
    owner_id = command.owner_id
    entity = await Repository.get_memory(
        session, memory_id=memory_id, conversation_id=conversation_id, owner_id=owner_id
    )
    return PersistenceMapper.memory_entity_to_info(entity)


async def list_memories(
    session: AsyncSession, command: Types.ListMemoriesCommand
) -> Types.MemoryPage[Types.MemoryInfo]:
    conversation_id = command.conversation_id
    owner_id = command.owner_id
    cursor = command.cursor
    limit = command.limit
    memory_types = command.memory_types
    page = await Repository.list_memories(
        session,
        conversation_id=conversation_id,
        owner_id=owner_id,
        cursor=cursor,
        limit=limit,
        memory_types=memory_types,
    )
    return PersistenceMapper.memory_page_row_to_info(page)


async def get_latest_summary(
    session: AsyncSession, command: Types.GetLatestSummaryCommand
) -> Types.MemoryInfo | None:
    conversation_id = command.conversation_id
    owner_id = command.owner_id
    entity = await Repository.get_latest_summary(
        session, conversation_id=conversation_id, owner_id=owner_id
    )
    return PersistenceMapper.memory_entity_to_info(entity)


async def search_memories(
    session: AsyncSession,
    query: Types.SearchMemoriesCommand,
    *,
    embedding_service: LLMService.EmbeddingService,
) -> list[Types.RetrievedMemoryInfo]:
    """Embed after authorization; provider failures propagate instead of looking empty.

    Caller supplies context-enriched query_text and configured embedding service.
    Extraction, query rewriting, thresholds and reranking remain deferred.
    """
    if not query.query_text.strip():
        raise ValueError("Memory search text must not be blank.")
    if not 1 <= query.top_k <= Repository.MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(
            f"top_k must be between 1 and {Repository.MAX_MEMORY_SEARCH_LIMIT}."
        )
    Repository.validate_memory_types(query.memory_types)
    if query.memory_types == ():
        return []
    if not await Repository.conversation_is_owned(
        session, conversation_id=query.conversation_id, owner_id=query.owner_id
    ):
        return []
    embedding = await embedding_service.embed_texts(
        LLMTypes.EmbedTextsCommand(
            texts=(query.query_text,),
            model=query.embedding_model,
            purpose=LLMTypes.EmbeddingPurpose.QUERY,
            provider=query.embedding_provider,
        )
    )
    if len(embedding.embeddings) != 1:
        raise ValueError("Memory query embedding must return exactly one vector.")
    if embedding.dimension != Repository.MEMORY_EMBEDDING_DIMENSION:
        raise ValueError(
            "Memory query embedding dimension is incompatible with stored vectors: "
            f"expected {Repository.MEMORY_EMBEDDING_DIMENSION}, "
            f"received {embedding.dimension}."
        )
    rows = await Repository.search_memories(
        session,
        conversation_id=query.conversation_id,
        owner_id=query.owner_id,
        query_embedding=embedding.embeddings[0],
        embedding_provider=embedding.provider.value,
        embedding_model=embedding.model,
        top_k=query.top_k,
        memory_types=query.memory_types,
    )
    return PersistenceMapper.memory_search_rows_to_info(rows)
