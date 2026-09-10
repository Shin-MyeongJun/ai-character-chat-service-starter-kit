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
