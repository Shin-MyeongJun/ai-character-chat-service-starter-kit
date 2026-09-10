from app.db.product_stats_queue import day_bounds
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import (
    generation as ChatGenerationQueryService,
)
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.commerce.billing import service as BillingService
from app.modules.commerce.billing import types as BillingTypes
from app.modules.content.product import types as Types
from app.modules.content.product.service.command import (
    statistics as ProductStatisticsCommandService,
)
from app.modules.content.product.service.command.statistics import enqueue_recent


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
        generation_facts = await ChatGenerationQueryService.get_statistics_facts(
            session, ChatTypes.GetStatisticsFactsCommand(product_id, start, end)
        )
        await ProductStatisticsCommandService.replace_statistics_day(
            session,
            Types.ReplaceStatisticsDayCommand(
                product_id=product_id,
                day=day,
                generations=generation_facts.generations,
                users=generation_facts.users,
                conversations=conversation_facts.conversations,
                transitions=conversation_facts.transitions,
                usage=billing_facts.usage,
                payments=billing_facts.payments,
            ),
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
            work = await ProductStatisticsCommandService.claim_statistics_work(session)
            if work is None:
                break
            await rebuild_day(
                session,
                Types.RebuildDayCommand(product_id=work.product_id, day=work.day),
            )
            await ProductStatisticsCommandService.complete_statistics_work(
                session,
                Types.RebuildDayCommand(product_id=work.product_id, day=work.day),
            )
        processed += 1
    return Types.ProcessedStatisticsInfo(processed)


__all__ = ["enqueue_recent", "process_pending", "rebuild_day"]
