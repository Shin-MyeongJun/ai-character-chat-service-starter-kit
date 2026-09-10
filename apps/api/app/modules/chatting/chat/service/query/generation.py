from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper


async def get_statistics_facts(
    session, command: Types.GetStatisticsFactsCommand
) -> Types.GenerationStatisticsInfo:
    rows = await Repository.get_statistics_facts(
        session, command.product_id, command.start, command.end
    )
    return PersistenceMapper.generation_statistics_rows_to_info(rows)
