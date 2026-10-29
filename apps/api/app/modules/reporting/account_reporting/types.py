"""영역별 조회 계약. 다른 reporting 영역과 결과 타입을 공유하지 않는다."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.core.reporting import PeriodInfo, ReportingError


@dataclass(frozen=True, slots=True)
class ActorCommand:
    """인증 경계가 제공한 내부 사용자 ID. 토큰 인증을 대체하지 않는다."""

    user_id: UUID


class ReportError(ReportingError):
    """이 영역의 권한·조회 실패."""


@dataclass(frozen=True, slots=True)
class GetAccountReportCommand:
    date_from: date
    date_to: date


@dataclass(frozen=True, slots=True)
class GenerationCountsInfo:
    pending: int
    succeeded: int
    failed: int
    cancelled: int
    stale: int


@dataclass(frozen=True, slots=True)
class RecordedUsageInfo:
    usage_records: int
    input_tokens: int
    output_tokens: int
    recorded_cost_credit: int
    credit_unit: str = "CREDIT"


@dataclass(frozen=True, slots=True)
class AccountReportView:
    """예약 코호트와 별도 usage 기록. empty는 양쪽 기록이 모두 없다는 뜻이다."""

    period: PeriodInfo
    queried_at: datetime
    generations: GenerationCountsInfo
    usage: RecordedUsageInfo
    state: str
    method: str = "saved_records_by_creation_time"
    consistency: str = "separate_read_queries"
