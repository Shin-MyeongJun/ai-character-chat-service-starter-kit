# 이벤트 시각을 서울 날짜로 변환해 상품/날짜 하나의 dirty 작업으로 합친다. 통계 계산 자체는 수행하지 않는다.
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
