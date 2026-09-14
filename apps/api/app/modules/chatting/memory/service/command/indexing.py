from __future__ import annotations

import hashlib
from math import isfinite

from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper
from app.modules.llm import service as LLMService
from app.modules.llm import types as LLMTypes


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class MemoryIndexer:
    def __init__(self, embedding_service: LLMService.EmbeddingService) -> None:
        self._embedding_service = embedding_service

    async def embed_summary(
        self, command: Types.EmbedSummaryCommand
    ) -> Types.EmbeddedSummaryInfo:
        if content_digest(command.content) != command.content_digest:
            raise Types.StaleMemoryWorkError("Summary content changed before indexing.")
        result = await self._embedding_service.embed_texts(
            LLMTypes.EmbedTextsCommand(
                texts=(command.content,),
                model=command.model,
                provider=command.provider,
                purpose=LLMTypes.EmbeddingPurpose.DOCUMENT,
                output_dimension=command.output_dimension,
                truncation=command.truncation,
            )
        )
        if len(result.embeddings) != 1:
            raise ValueError("Summary embedding must return exactly one vector.")
        vector = result.embeddings[0]
        if (
            result.dimension != Repository.MEMORY_EMBEDDING_DIMENSION
            or len(vector) != result.dimension
            or not all(isfinite(value) for value in vector)
            or not any(vector)
        ):
            raise ValueError(
                "Summary embedding is incompatible with the memory vector column."
            )
        return Types.EmbeddedSummaryInfo(
            memory_id=command.memory_id,
            conversation_id=command.conversation_id,
            owner_id=command.owner_id,
            content_digest=command.content_digest,
            conversation_revision=command.conversation_revision,
            vector=vector,
            provider=result.provider,
            model=result.model,
            dimension=result.dimension,
            settings={
                "purpose": "document",
                "truncation": command.truncation,
                "output_dimension": command.output_dimension,
                "output_dtype": "float",
            },
            total_tokens=result.usage.total_tokens,
        )


async def save_summary_embedding(
    session, command: Types.SaveEmbeddingCommand
) -> Types.MemoryInfo:
    current_row = await Repository.get_memory(
        session,
        memory_id=command.value.memory_id,
        conversation_id=command.value.conversation_id,
        owner_id=command.value.owner_id,
        for_update=True,
    )
    current = PersistenceMapper.memory_entity_to_info(current_row)
    if (
        current is None
        or current.conversation_revision != command.value.conversation_revision
        or content_digest(current.content) != command.value.content_digest
    ):
        raise Types.StaleMemoryWorkError(
            "Summary disappeared or changed before indexing."
        )
    row = await Repository.save_embedding(session, value=command.value)
    info = PersistenceMapper.memory_entity_to_info(row)
    if info is None:
        raise Types.StaleMemoryWorkError("Summary disappeared or was invalidated.")
    return info
