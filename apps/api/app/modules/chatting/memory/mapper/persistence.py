from typing import cast, overload

from app.db.models.memory import ConversationMemory
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
    )


@overload
def memory_entity_to_retrieved(
    entity: ConversationMemory, *, similarity_score: float
) -> Types.RetrievedMemoryInfo: ...


@overload
def memory_entity_to_retrieved(entity: None, *, similarity_score: float) -> None: ...


def memory_entity_to_retrieved(
    entity: ConversationMemory | None, *, similarity_score: float
) -> Types.RetrievedMemoryInfo | None:
    if entity is None:
        return None
    "Accept a similarity score, not a raw vector distance."
    return Types.RetrievedMemoryInfo(
        memory_id=entity.id,
        memory_type=cast(Types.MemoryType, entity.memory_type),
        content=entity.content,
        similarity_score=similarity_score,
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
