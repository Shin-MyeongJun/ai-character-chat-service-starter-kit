from typing import cast, overload

from app.db.models.memory import ConversationMemory, MemoryJob
from app.modules.chatting.memory import types as Types


@overload
def memory_entity_to_info(entity: ConversationMemory) -> Types.MemoryInfo: ...


@overload
def memory_entity_to_info(entity: None) -> None: ...


def memory_entity_to_info(entity: ConversationMemory | None) -> Types.MemoryInfo | None:
    if entity is None:
        return None
    return Types.MemoryInfo(
        id=entity.id,
        conversation_id=entity.conversation_id,
        memory_type=cast(Types.MemoryType, entity.memory_type),
        content=entity.content,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        index_status=cast(Types.MemoryIndexStatus, entity.index_status),
        importance=entity.importance,
        source_start_position=entity.source_start_position,
        source_end_position=entity.source_end_position,
        source_digest=entity.source_digest,
        conversation_revision=entity.conversation_revision,
        summary_provider=entity.summary_provider,
        summary_model=entity.summary_model,
        prompt_version=entity.prompt_version,
        embedding_provider=entity.embedding_provider,
        embedding_model=entity.embedding_model,
        embedding_dimension=entity.embedding_dimension,
    )


def memory_entity_to_retrieved(
    entity: ConversationMemory, *, similarity_score: float
) -> Types.RetrievedMemoryInfo:
    return Types.RetrievedMemoryInfo(
        memory_id=entity.id,
        memory_type=cast(Types.MemoryType, entity.memory_type),
        content=entity.content,
        similarity_score=similarity_score,
        importance=entity.importance,
        source_start_position=entity.source_start_position,
        source_end_position=entity.source_end_position,
        source_digest=entity.source_digest,
        conversation_revision=entity.conversation_revision,
        summary_provider=entity.summary_provider,
        summary_model=entity.summary_model,
        prompt_version=entity.prompt_version,
        embedding_provider=entity.embedding_provider,
        embedding_model=entity.embedding_model,
        embedding_dimension=entity.embedding_dimension,
        created_at=entity.created_at,
    )


def memory_page_row_to_info(page) -> Types.MemoryPage[Types.MemoryInfo]:
    return Types.MemoryPage(
        items=[memory_entity_to_info(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


def memory_search_rows_to_info(rows) -> list[Types.RetrievedMemoryInfo]:
    return [
        memory_entity_to_retrieved(entity, similarity_score=score)
        for entity, score in rows
    ]


@overload
def memory_job_entity_to_work(entity: MemoryJob) -> Types.MemoryWorkInfo: ...


@overload
def memory_job_entity_to_work(entity: None) -> None: ...


def memory_job_entity_to_work(entity: MemoryJob | None) -> Types.MemoryWorkInfo | None:
    if entity is None:
        return None
    assert entity.scope_generation is not None
    assert entity.lease_owner is not None
    return Types.MemoryWorkInfo(
        conversation_id=entity.conversation_id,
        owner_id=entity.owner_id,
        scope_generation=entity.scope_generation,
        attempt_count=entity.attempt_count,
        lease_owner=entity.lease_owner,
    )
