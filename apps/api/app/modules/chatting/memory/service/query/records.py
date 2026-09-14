from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.memory import repository as Repository
from app.modules.chatting.memory import types as Types
from app.modules.chatting.memory.mapper import persistence as PersistenceMapper


async def get_memory(
    session: AsyncSession, command: Types.GetMemoryCommand
) -> Types.MemoryInfo | None:
    row = await Repository.get_memory(
        session,
        memory_id=command.memory_id,
        conversation_id=command.conversation_id,
        owner_id=command.owner_id,
    )
    return PersistenceMapper.memory_entity_to_info(row)


async def list_memories(
    session: AsyncSession, command: Types.ListMemoriesCommand
) -> Types.MemoryPage[Types.MemoryInfo]:
    page = await Repository.list_memories(
        session,
        conversation_id=command.conversation_id,
        owner_id=command.owner_id,
        cursor=command.cursor,
        limit=command.limit,
        memory_types=command.memory_types,
    )
    return PersistenceMapper.memory_page_row_to_info(page)


async def get_latest_summary(
    session: AsyncSession, command: Types.GetLatestSummaryCommand
) -> Types.MemoryInfo | None:
    row = await Repository.get_latest_summary(
        session, conversation_id=command.conversation_id, owner_id=command.owner_id
    )
    return PersistenceMapper.memory_entity_to_info(row)


async def get_pending_index(
    session: AsyncSession, command: Types.GetPendingIndexCommand
) -> Types.MemoryInfo | None:
    row = await Repository.get_pending_index(
        session, conversation_id=command.conversation_id, owner_id=command.owner_id
    )
    return PersistenceMapper.memory_entity_to_info(row)
