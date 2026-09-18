# 사용자 범위의 생성 상태와 상품 통계용 생성 사실을 반환한다. 통계 조회는 내부 조율용이다.
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper


async def get_generation_state(
    session, command: Types.GetGenerationStateCommand
) -> Types.GenerationStateInfo:
    row = await Repository.get_owned_generation(
        session, command.generation_id, command.user_id
    )
    info = PersistenceMapper.generation_entity_to_state_info(row)
    if info is None:
        raise LookupError("Generation not found.")
    return info


async def get_statistics_facts(
    session, command: Types.GetStatisticsFactsCommand
) -> Types.GenerationStatisticsInfo:
    rows = await Repository.get_statistics_facts(
        session, command.product_id, command.start, command.end
    )
    return PersistenceMapper.generation_statistics_rows_to_info(rows)
