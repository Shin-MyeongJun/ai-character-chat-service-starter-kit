"""공개 도메인 값만 조합하는 본인 사용량 mapper."""

from datetime import datetime

from app.core.reporting import PeriodInfo
from app.modules.chatting.chat import types as ChatTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.reporting.account_reporting import types as Types


def generation_usage_infos_to_view(
    generations: ChatTypes.AccountGenerationStatisticsInfo,
    usage: BillingTypes.AccountUsageStatisticsInfo,
    period: PeriodInfo,
    queried_at: datetime,
) -> Types.AccountReportView:
    """생성 코호트와 별도 usage 기록을 구분하고 기록이 전혀 없는 결과를 empty로 표시한다."""
    counts = Types.GenerationCountsInfo(
        pending=generations.pending,
        succeeded=generations.succeeded,
        failed=generations.failed,
        cancelled=generations.cancelled,
        stale=generations.stale,
    )
    recorded = Types.RecordedUsageInfo(
        usage_records=usage.usage_records,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        recorded_cost_credit=usage.recorded_cost_credit,
    )
    state = (
        "empty"
        if not any(
            (
                counts.pending,
                counts.succeeded,
                counts.failed,
                counts.cancelled,
                counts.stale,
            )
        )
        and not recorded.usage_records
        else "recorded"
    )
    return Types.AccountReportView(period, queried_at, counts, recorded, state)
