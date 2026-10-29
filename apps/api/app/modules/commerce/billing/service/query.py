# 상품 통계 유스케이스에 청구 도메인의 원시 집계값을 제공한다.
# 결과 변환 후 합산은 product가 담당한다.
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.billing import repository as Repository
from app.modules.commerce.billing import types as Types
from app.modules.commerce.billing.mapper import persistence as PersistenceMapper


async def get_statistics_facts(
    session: AsyncSession, command: Types.GetStatisticsFactsCommand
) -> Types.BillingStatisticsInfo:
    rows = await Repository.get_statistics_facts(
        session, command.product_id, command.start, command.end
    )
    return PersistenceMapper.billing_statistics_rows_to_info(rows)


async def get_account_usage_statistics(
    session: AsyncSession, command: Types.GetAccountUsageStatisticsCommand
) -> Types.AccountUsageStatisticsInfo:
    """활성 사용자의 기록된 토큰·청구 크레딧을 usage 생성 시각 범위로 조회한다."""
    from app.core.reporting import validate_reporting_times
    from app.modules.identity import types as IdentityTypes
    from app.modules.identity.service import query as IdentityQueryService

    with session.no_autoflush:
        validate_reporting_times(command.start, command.end)
        await IdentityQueryService.require_active_user(
            session, IdentityTypes.GetUserCommand(user_id=command.user_id)
        )
        row = await Repository.get_account_usage_statistics(
            session, command.user_id, command.start, command.end
        )
        return PersistenceMapper.account_usage_statistics_row_to_info(row)
