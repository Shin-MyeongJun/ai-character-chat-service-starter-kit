"""공개 도메인 값만 조합하는 본인 사용량 mapper."""

from dataclasses import fields

from app.modules.reporting.account_reporting import types as Types


def generation_usage_infos_to_view(
    generations, usage, period, queried_at
) -> Types.AccountReportView:
    """생성 코호트와 별도 usage 기록을 구분하고 기록이 전혀 없는 결과를 empty로 표시한다."""
    counts = Types.GenerationCountsInfo(
        **{
            field.name: getattr(generations, field.name)
            for field in fields(Types.GenerationCountsInfo)
        }
    )
    recorded = Types.RecordedUsageInfo(
        usage.usage_records,
        usage.input_tokens,
        usage.output_tokens,
        usage.recorded_cost_credit,
    )
    state = (
        "empty"
        if not any(getattr(counts, field.name) for field in fields(counts))
        and not recorded.usage_records
        else "recorded"
    )
    return Types.AccountReportView(period, queried_at, counts, recorded, state)
