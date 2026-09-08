from typing import cast

from app.db.models.memory import ConversationMemory
from app.modules.chatting.memory import types


def memory_create_to_entity(command: types.CreateMemoryCommand) -> ConversationMemory:
    """Map content only; the service must authorize access to the conversation."""
    return ConversationMemory(
        conversation_id=command.conversation_id,
        memory_type=command.memory_type,
        content=command.content,
    )


def apply_memory_update_to_entity(
    entity: ConversationMemory,
    command: types.UpdateMemoryCommand,
) -> ConversationMemory:
    """Apply an authorized update and invalidate the old content's embedding."""
    if entity.content != command.content:
        entity.content = command.content
        entity.embedding = None
    return entity


def memory_entity_to_info(entity: ConversationMemory) -> types.MemoryInfo:
    return types.MemoryInfo(
        id=entity.id,
        conversation_id=entity.conversation_id,
        memory_type=cast(types.MemoryType, entity.memory_type),
        content=entity.content,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def memory_entity_to_retrieved(
    entity: ConversationMemory,
    *,
    similarity_score: float,
) -> types.RetrievedMemory:
    """Accept a similarity score, not a raw vector distance."""
    return types.RetrievedMemory(
        memory_id=entity.id,
        memory_type=cast(types.MemoryType, entity.memory_type),
        content=entity.content,
        similarity_score=similarity_score,
    )
