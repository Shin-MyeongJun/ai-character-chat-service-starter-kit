# 상품 통계 유스케이스에 청구 도메인의 원시 집계값을 제공한다. 결과 변환 후 합산은 product가 담당한다.
from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import persistence as PersistenceMapper


async def get_statistics_facts(
    session, command: Types.GetStatisticsFactsCommand
) -> Types.BillingStatisticsInfo:
    rows = await Repository.get_statistics_facts(
        session, command.product_id, command.start, command.end
    )
    return PersistenceMapper.billing_statistics_rows_to_info(rows)
