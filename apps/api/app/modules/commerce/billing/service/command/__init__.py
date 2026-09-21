# generation 저장 흐름에서 사용량 행을 추가한다.
# 상위 use_case_transaction이 있으면 그 경계에 참여한다.
# 이 호출만으로 결제나 크레딧 잔액 차감은 일어나지 않는다.
from app.db.transaction import use_case_transaction
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import persistence as PersistenceMapper


async def record_usage(
    session, command: Types.RecordUsageCommand
) -> Types.UsageRecordedInfo:
    async with use_case_transaction(session):
        row = await Repository.create_usage_log(session, command)
        return PersistenceMapper.usage_entity_to_info(row)
