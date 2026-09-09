from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Visibility = Literal["private", "public", "unlisted"]


class ResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ListProductsRequestDto(RequestDto):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=100)


class ProductStatisticsRequestDto(RequestDto):
    date_from: date
    date_to: date
    snapshot_id: UUID | None = None


class ProductWriteRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20000)
    opening_message: str | None = Field(default=None, max_length=20000)
    visibility: Visibility = "private"


class ModelNoticeResponseDto(ResponseDto):
    state: str
    reason: str | None = None
    model_id: UUID | None = None
    model_name: str | None = None
    announced_at: datetime | None = None
    shutdown_at: datetime | None = None
    transition_deadline: datetime | None = None
    replacement_model_id: UUID | None = None
    replacement_model_name: str | None = None
    replacement_reasoning_effort: str | None = None
    unavailable_policy: str | None = None


class ProductInfoResponseDto(ResponseDto):
    id: UUID
    title: str
    description: str | None
    opening_message: str | None
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime


class CharacterSelectionResponseDto(ResponseDto):
    character_id: UUID
    is_primary: bool = False
    role_name: str | None = None


class LorebookSelectionResponseDto(ResponseDto):
    lorebook_id: UUID
    scope: Literal["all", "selected"] = "all"
    character_ids: tuple[UUID, ...] = ()
    role: Literal["main", "detail", "rule", "optional"] = "detail"
    priority: int = 0
    is_required: bool = True


class CompositionResponseDto(ResponseDto):
    characters: tuple[CharacterSelectionResponseDto, ...] = ()
    lorebooks: tuple[LorebookSelectionResponseDto, ...] = ()


class SettingsResponseDto(ResponseDto):
    model_id: UUID
    reasoning_effort: str
    start_entry_ids: tuple[UUID, ...]
    replacement_scope: Literal["same_family", "same_provider", "allowlist"] = (
        "same_family"
    )
    replacement_model_ids: tuple[UUID, ...] = ()
    unavailable_policy: Literal["pause", "use_original_until_shutdown"] = "pause"


class ReleaseInfoResponseDto(ResponseDto):
    snapshot_id: UUID
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str


class StartOptionInfoResponseDto(ResponseDto):
    id: UUID
    title: str


class PublishedProductInfoResponseDto(ResponseDto):
    product_id: UUID
    snapshot_id: UUID
    version: int
    title: str
    description: str | None
    start_options: list[StartOptionInfoResponseDto]
    model_notice: ModelNoticeResponseDto | None


class UpdateInfoResponseDto(ResponseDto):
    snapshot_id: UUID
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str
    expires_at: datetime | None


class PendingUpdatesInfoResponseDto(ResponseDto):
    current_snapshot_id: UUID
    current_expires_at: datetime | None
    expiry_reason: str | None
    latest_snapshot_id: UUID | None
    updates: list[UpdateInfoResponseDto]
    model_notice: ModelNoticeResponseDto | None


class VersionAvailabilityInfoResponseDto(ResponseDto):
    snapshot_id: UUID
    expires_at: datetime | None
    expiry_reason: str | None
    model_notice: ModelNoticeResponseDto | None


class RevenueInfoResponseDto(ResponseDto):
    sales: str
    refunds: str
    net: str
    sale_count: int
    refund_count: int


class StatisticsMetricsResponseDto(ResponseDto):
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
    revenue: dict[str, RevenueInfoResponseDto]


class StatisticsDayInfoResponseDto(StatisticsMetricsResponseDto):
    day: date
    updated_at: datetime


class StatisticsInfoResponseDto(ResponseDto):
    product_id: UUID
    snapshot_id: UUID | None
    timezone: str
    date_from: date
    date_to: date
    totals: StatisticsMetricsResponseDto
    pending_days: list[date]
    days: list[StatisticsDayInfoResponseDto]


class CharacterSelectionRequestDto(RequestDto):
    character_id: UUID
    is_primary: bool = False
    role_name: str | None = Field(default=None, max_length=200)


class LorebookSelectionRequestDto(RequestDto):
    lorebook_id: UUID
    scope: Literal["all", "selected"] = "all"
    character_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    role: Literal["main", "detail", "rule", "optional"] = "detail"
    priority: int = Field(default=0, ge=-(2**31), lt=2**31)
    is_required: bool = True


class CompositionRequestDto(RequestDto):
    characters: tuple[CharacterSelectionRequestDto, ...] = Field(
        default=(), max_length=100
    )
    lorebooks: tuple[LorebookSelectionRequestDto, ...] = Field(
        default=(), max_length=100
    )


class SettingsRequestDto(RequestDto):
    model_id: UUID
    reasoning_effort: str
    start_entry_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    replacement_scope: Literal["same_family", "same_provider", "allowlist"] = (
        "same_family"
    )
    replacement_model_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    unavailable_policy: Literal["pause", "use_original_until_shutdown"] = "pause"


class ReleaseRequestDto(RequestDto):
    summary: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    auto_apply_media: bool = False
