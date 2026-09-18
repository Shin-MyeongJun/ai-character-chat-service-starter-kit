# 호환 ready 기억이 있을 때만 query 임베딩을 호출하고 관련도·중요도·최근성으로 예산 안에서 선택한다.
# MemoryRetriever는 외부 호출 전 세션을 닫는다. 호환 함수 search_memories는 전달받은 세션을 유지한다.
"""Authorized semantic retrieval and explainable Hypha selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper
from app.modules.chatting.memory.service.command.summarization import estimate_tokens
from app.modules.llm import service as LLMService
from app.modules.llm import types as LLMTypes


class MemoryRetriever:
    """Run authorization/read, provider I/O, and vector read in separate sessions."""

    def __init__(
        self, session_factory, embedding_service: LLMService.EmbeddingService
    ) -> None:
        self._session_factory = session_factory
        self._embedding_service = embedding_service

    # 인가·호환 기억 존재 확인 후 세션을 닫고 query 임베딩을 호출한다. 없으면 외부 호출 없이 빈 결과다.
    async def retrieve_memories(
        self, command: Types.SearchMemoriesCommand
    ) -> list[Types.RetrievedMemoryInfo]:
        _validate_search(command)
        if command.memory_types == () or command.token_budget == 0:
            return []
        provider = (
            LLMTypes.EmbeddingProvider(command.embedding_provider).value
            if command.embedding_provider is not None
            else None
        )
        async with self._session_factory() as session:
            if not await Repository.conversation_is_owned(
                session,
                conversation_id=command.conversation_id,
                owner_id=command.owner_id,
            ):
                return []
            exists = await Repository.has_searchable_memories(
                session,
                conversation_id=command.conversation_id,
                owner_id=command.owner_id,
                embedding_provider=provider,
                embedding_model=command.embedding_model,
                embedding_dimension=Repository.MEMORY_EMBEDDING_DIMENSION,
                memory_types=command.memory_types,
            )
        if not exists:
            return []
        embedding = await self._embedding_service.embed_texts(
            LLMTypes.EmbedTextsCommand(
                texts=(command.query_text,),
                model=command.embedding_model,
                purpose=LLMTypes.EmbeddingPurpose.QUERY,
                provider=command.embedding_provider,
                output_dimension=command.output_dimension,
            )
        )
        _validate_query_embedding(embedding)
        async with self._session_factory() as session:
            rows = await Repository.search_memories(
                session,
                conversation_id=command.conversation_id,
                owner_id=command.owner_id,
                query_embedding=embedding.embeddings[0],
                embedding_provider=embedding.provider.value,
                embedding_model=embedding.model,
                top_k=command.top_k,
                memory_types=command.memory_types,
            )
        candidates = PersistenceMapper.memory_search_rows_to_info(rows)
        return _select_memories(
            candidates,
            command.token_budget,
            result_limit=command.result_limit,
            conservative=command.conservative_token_budget,
            now=datetime.now(UTC),
        )


def _validate_search(query: Types.SearchMemoriesCommand) -> None:
    if not query.query_text.strip():
        raise ValueError("Memory search text must not be blank.")
    if not 1 <= query.top_k <= Repository.MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(
            f"top_k must be between 1 and {Repository.MAX_MEMORY_SEARCH_LIMIT}."
        )
    if query.token_budget is not None and query.token_budget < 0:
        raise ValueError("Memory token budget must not be negative.")
    if query.result_limit is not None and not 1 <= query.result_limit <= query.top_k:
        raise ValueError("Memory result limit must be between 1 and top_k.")
    Repository.validate_memory_types(query.memory_types)


def _validate_query_embedding(embedding: LLMTypes.EmbeddingResultInfo) -> None:
    if len(embedding.embeddings) != 1:
        raise ValueError("Memory query embedding must return exactly one vector.")
    if embedding.dimension != Repository.MEMORY_EMBEDDING_DIMENSION:
        raise ValueError(
            "Memory query embedding dimension is incompatible with stored vectors: "
            f"expected {Repository.MEMORY_EMBEDDING_DIMENSION}, received {embedding.dimension}."
        )


# 기존 호출자를 위한 세션 주입 경로다. 외부 호출 전 세션을 닫는 책임까지 맡지 않는다.
async def search_memories(
    session: AsyncSession,
    query: Types.SearchMemoriesCommand,
    *,
    embedding_service: LLMService.EmbeddingService,
) -> list[Types.RetrievedMemoryInfo]:
    _validate_search(query)
    if query.memory_types == () or query.token_budget == 0:
        return []
    if not await Repository.conversation_is_owned(
        session, conversation_id=query.conversation_id, owner_id=query.owner_id
    ):
        return []
    provider = (
        LLMTypes.EmbeddingProvider(query.embedding_provider).value
        if query.embedding_provider is not None
        else None
    )
    if not await Repository.has_searchable_memories(
        session,
        conversation_id=query.conversation_id,
        owner_id=query.owner_id,
        embedding_provider=provider,
        embedding_model=query.embedding_model,
        embedding_dimension=Repository.MEMORY_EMBEDDING_DIMENSION,
        memory_types=query.memory_types,
    ):
        return []
    embedding = await embedding_service.embed_texts(
        LLMTypes.EmbedTextsCommand(
            texts=(query.query_text,),
            model=query.embedding_model,
            purpose=LLMTypes.EmbeddingPurpose.QUERY,
            provider=query.embedding_provider,
            output_dimension=query.output_dimension,
        )
    )
    _validate_query_embedding(embedding)
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
    candidates = PersistenceMapper.memory_search_rows_to_info(rows)
    return _select_memories(
        candidates,
        query.token_budget,
        result_limit=query.result_limit,
        conservative=query.conservative_token_budget,
        now=datetime.now(UTC),
    )


def _select_memories(
    candidates: list[Types.RetrievedMemoryInfo],
    token_budget: int | None,
    *,
    result_limit: int | None = None,
    now: datetime,
    conservative: bool = False,
) -> list[Types.RetrievedMemoryInfo]:
    deduplicated: dict[str, Types.RetrievedMemoryInfo] = {}
    for item in candidates:
        age_days = 3650.0
        if item.created_at is not None:
            created = item.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age_days = max(0.0, (now - created).total_seconds() / 86400)
        recency = 1.0 / (1.0 + age_days / 30.0)
        score = 0.65 * item.similarity_score + 0.2 * item.importance + 0.15 * recency
        enriched = replace(
            item,
            recency_score=recency,
            selection_score=score,
            estimated_tokens=estimate_rendered_memory_tokens(item.content)
            if conservative
            else estimate_tokens(item.content),
        )
        key = hashlib.sha256(item.content.strip().casefold().encode()).hexdigest()
        previous = deduplicated.get(key)
        if previous is None or enriched.selection_score > previous.selection_score:
            deduplicated[key] = enriched
    ranked = sorted(
        deduplicated.values(),
        key=lambda item: (-item.selection_score, str(item.memory_id)),
    )
    selected: list[Types.RetrievedMemoryInfo] = []
    used = 0
    for item in ranked:
        if result_limit is not None and len(selected) >= result_limit:
            break
        if token_budget is not None and used + item.estimated_tokens > token_budget:
            continue
        selected.append(item)
        used += item.estimated_tokens
    return sorted(
        selected,
        key=lambda item: (
            item.source_end_position is None,
            item.source_end_position or 0,
            item.created_at or datetime.min.replace(tzinfo=UTC),
            str(item.memory_id),
        ),
    )


def estimate_rendered_memory_tokens(content: str) -> int:
    """UTF-8 JSON bytes including quotes and a comma/separator reserve."""
    return len(json.dumps(content, ensure_ascii=False).encode()) + 2
