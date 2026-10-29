"""영역별 조회 계약. 다른 reporting 영역과 결과 타입을 공유하지 않는다."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.core.reporting import FreshnessInfo, PeriodInfo, ReportingError


@dataclass(frozen=True, slots=True)
class ActorCommand:
    """인증 경계가 제공한 내부 사용자 ID. 토큰 인증을 대체하지 않는다."""

    user_id: UUID


class ReportError(ReportingError):
    """이 영역의 권한·조회 실패."""


@dataclass(frozen=True, slots=True)
class GetCreatorProductReportCommand:
    product_id: UUID
    date_from: date
    date_to: date
    snapshot_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreatorMetricsInfo:
    active_users: int
    succeeded: int
    failed: int
    cancelled: int
    stale: int
    messages: int
    conversations: int
    transitions: int
    input_tokens: int
    output_tokens: int
    cost_credit: int


@dataclass(frozen=True, slots=True)
class CreatorDayInfo:
    """metrics=None은 미집계이며, pending 날짜의 저장 값은 stale일 수 있다."""

    day: date
    metrics: CreatorMetricsInfo | None
    updated_at: datetime | None
    state: str


@dataclass(frozen=True, slots=True)
class CreatorProductReportView:
    """기간 DISTINCT를 보존한 작가 전용 값. 부분 합계와 확정 totals를 구분한다."""

    product_id: UUID
    snapshot_id: UUID | None
    period: PeriodInfo
    queried_at: datetime
    totals: CreatorMetricsInfo | None
    recorded_totals: CreatorMetricsInfo | None
    days: tuple[CreatorDayInfo, ...]
    freshness: FreshnessInfo
    credit_unit: str = "CREDIT"
    consistency: str = "separate_read_queries"
