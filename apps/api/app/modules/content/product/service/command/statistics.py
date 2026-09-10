from datetime import UTC, datetime, timedelta

from app.db.product_stats_queue import day_bounds, statistics_day
from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.commerce.billing import service as BillingService
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import repository as Repository
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.mapper import statistics as StatisticsMapper
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)


async def rebuild_day(session, command: Types.RebuildDayCommand) -> None:
    async with use_case_transaction(session):
        product_id = command.product_id
        day = command.day
        start, end = day_bounds(day)
        conversation_facts = await ConversationService.get_statistics_facts(
            session, ConversationTypes.GetStatisticsFactsCommand(product_id, start, end)
        )
        billing_facts = await BillingService.get_statistics_facts(
            session, BillingTypes.GetStatisticsFactsCommand(product_id, start, end)
        )
        build = StatisticsMapper.statistics_facts_infos_to_build_info(
            conversation_facts, billing_facts
        )
        await Repository.replace_statistics_day(
            session, product_id, day, build, datetime.now(UTC)
        )


async def process_pending(
    session, command: Types.ProcessPendingCommand
) -> Types.ProcessedStatisticsInfo:
    limit = command.limit
    if not 1 <= limit <= 1000:
        raise ValueError("Batch limit must be 1–1000.")
    processed = 0
    for _ in range(limit):
        async with use_case_transaction(session):
            row = await Repository.get_pending_statistics_work(session)
            work = PersistenceMapper.statistics_work_entity_to_info(row)
            if work is None:
                break
            await rebuild_day(
                session,
                Types.RebuildDayCommand(product_id=work.product_id, day=work.day),
            )
            await Repository.delete_statistics_work(session, work.product_id, work.day)
        processed += 1
    return Types.ProcessedStatisticsInfo(processed)


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
