"""영역별 조회 계약. 다른 reporting 영역과 결과 타입을 공유하지 않는다."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from app.core.reporting import FreshnessInfo, PeriodInfo, ReportingError


@dataclass(frozen=True, slots=True)
class ActorCommand:
    """인증 경계가 제공한 내부 사용자 ID. 토큰 인증을 대체하지 않는다."""

    user_id: UUID


@dataclass(frozen=True, slots=True)
class ListGenerationPromptsCommand:
    date_from: date
    date_to: date
    conversation_id: UUID | None = None
    status: str | None = None
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True, slots=True)
class GetGenerationPromptCommand:
    generation_id: UUID


@dataclass(frozen=True, slots=True)
class GenerationPromptSummaryView:
    generation_id: UUID
    conversation_id: UUID
    model_id: UUID
    model_name: str
    reasoning_effort: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    history_invalidated_at: datetime | None
    prompt_recorded: bool
    prompt_created_at: datetime | None
    provider: str | None


@dataclass(frozen=True, slots=True)
class GenerationPromptView:
    request_json: str
    digest: str
    format_version: int
    created_at: datetime
    provider: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class GenerationPromptPageView:
    items: tuple[GenerationPromptSummaryView, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class GenerationPromptDetailView:
    generation: GenerationPromptSummaryView
    prompt: GenerationPromptView | None


class ReportError(ReportingError):
    """이 영역의 권한·조회 실패."""


@dataclass(frozen=True, slots=True)
class GetOperationsProductReportCommand:
    product_id: UUID
    date_from: date
    date_to: date
    snapshot_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class OperationsMetricsInfo:
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
class OperationsDayInfo:
    day: date
    metrics: OperationsMetricsInfo | None
    updated_at: datetime | None
    state: str


@dataclass(frozen=True, slots=True)
class OperationsProductReportView:
    product_id: UUID
    snapshot_id: UUID | None
    period: PeriodInfo
    queried_at: datetime
    totals: OperationsMetricsInfo | None
    recorded_totals: OperationsMetricsInfo | None
    days: tuple[OperationsDayInfo, ...]
    freshness: FreshnessInfo
    credit_unit: str = "CREDIT"
    consistency: str = "separate_read_queries"


@dataclass(frozen=True, slots=True)
class GetRecordedServiceReportCommand:
    date_from: date
    date_to: date


@dataclass(frozen=True, slots=True)
class RecordedServiceReportView:
    period: PeriodInfo
    queried_at: datetime
    recorded_totals: OperationsMetricsInfo | None
    product_days: int
    products_with_rows: int
    pending_product_days: int
    oldest_pending_at: datetime | None
    freshness: FreshnessInfo
    coverage: str = "all_product_day_coverage_not_verified"
    consistency: str = "separate_read_queries"
    credit_unit: str = "CREDIT"


@dataclass(frozen=True, slots=True)
class StatisticsQueueReportView:
    pending_product_days: int
    oldest_requested_at: datetime | None
    oldest_latest_request_age_seconds: float | None
    queried_at: datetime
