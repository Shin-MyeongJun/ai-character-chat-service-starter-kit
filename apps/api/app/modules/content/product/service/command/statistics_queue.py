from app.db.product_stats_queue import statistics_day
from app.db.transaction import use_case_transaction
from app.modules.content.product import types as Types
from app.modules.content.product.repository import statistics as StatisticsRepository


async def mark_statistics_dirty(
    session, command: Types.MarkStatisticsDirtyCommand
) -> None:
    day = statistics_day(command.instant)
    async with use_case_transaction(session):
        await StatisticsRepository.upsert_statistics_work(
            session, command.product_id, day
        )
