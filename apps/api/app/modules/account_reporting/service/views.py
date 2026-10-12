"""영역별 권한과 공개 도메인 조회를 조합한다. HTTP/DB 쓰기를 수행하지 않는다."""

from datetime import UTC, datetime
from uuid import UUID

from app.core.reporting import get_reporting_period
from app.modules.account_reporting import types as Types
from app.modules.account_reporting.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import (
    generation as ChatGenerationQueryService,
)
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import query as BillingQueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def get_account_report(
    session, command: Types.GetAccountReportCommand, *, actor: Types.ActorCommand
) -> Types.AccountReportView:
    """활성 사용자의 저장된 생성/usage를 각각의 생성 시각 범위로 조회한다.

    chat의 예약 코호트 상태와 billing의 usage 기록은 기간 기준이 달라
    성공 생성 수와 usage 행 수가 같다고 가정하지 않는다. 토큰은 공급자 총청구가 아니다.
    """
    period = get_reporting_period(command.date_from, command.date_to)
    with session.no_autoflush:
        if not isinstance(actor.user_id, UUID):
            raise Types.ReportError("invalid_input")
        try:
            await IdentityQueryService.require_active_user(
                session, IdentityTypes.GetUserCommand(actor.user_id)
            )
        except LookupError as exc:
            raise Types.ReportError("forbidden") from exc
        # 원본 도메인이 SQL에서 본인 범위를 제한한다. 전체 사실을 읽고 거르지 않는다.
        generations = (
            await ChatGenerationQueryService.get_account_generation_statistics(
                session,
                ChatTypes.GetAccountGenerationStatisticsCommand(
                    actor.user_id, period.start, period.end
                ),
            )
        )
        usage = await BillingQueryService.get_account_usage_statistics(
            session,
            BillingTypes.GetAccountUsageStatisticsCommand(
                actor.user_id, period.start, period.end
            ),
        )
        return PersistenceMapper.generation_usage_infos_to_view(
            generations, usage, period, datetime.now(UTC)
        )
