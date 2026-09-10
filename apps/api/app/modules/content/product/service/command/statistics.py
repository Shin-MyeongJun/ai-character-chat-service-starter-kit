from datetime import UTC, datetime, timedelta

from app.db.product_stats_queue import day_bounds, statistics_day
from app.db.transaction import use_case_transaction
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.mapper import statistics as StatisticsMapper
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)


async def replace_statistics_day(
    session, command: Types.ReplaceStatisticsDayCommand
) -> None:
    async with use_case_transaction(session):
        build = StatisticsMapper.statistics_facts_infos_to_build_info(command)
        await Repository.replace_statistics_day(
            session, command.product_id, command.day, build, datetime.now(UTC)
        )


async def claim_statistics_work(session) -> Types.StatisticsWorkInfo | None:
    row = await Repository.get_pending_statistics_work(session)
    return PersistenceMapper.statistics_work_entity_to_info(row)


async def complete_statistics_work(session, command: Types.RebuildDayCommand) -> None:
    await Repository.delete_statistics_work(session, command.product_id, command.day)


async def enqueue_recent(session, command: Types.EnqueueRecentCommand) -> None:
    days = command.days
    now = command.now
    if not 1 <= days <= 31:
        raise ValueError("Repair range must be 1–31 days.")
    today = statistics_day(now or datetime.now(UTC))
    async with use_case_transaction(session):
        product_ids = await Repository.list_published_product_ids(session)
        for pid in product_ids:
            for offset in range(days + 1):
                start, _ = day_bounds(today - timedelta(days=offset))
                await mark_statistics_dirty(
                    session, Types.MarkStatisticsDirtyCommand(pid, start)
                )
