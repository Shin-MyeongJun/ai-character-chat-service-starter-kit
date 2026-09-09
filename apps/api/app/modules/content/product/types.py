from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.modules.llm.types import ModelNotice

Visibility = Literal["private", "public", "unlisted"]


@dataclass(frozen=True, slots=True)
class ProductWrite:
    title: str
    description: str | None = None
    opening_message: str | None = None
    visibility: Visibility = "private"


@dataclass(frozen=True, slots=True)
class ProductListQuery:
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ProductStatisticsQuery:
    date_from: date
    date_to: date
    snapshot_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProductInfo:
    id: UUID
    title: str
    description: str | None
    opening_message: str | None
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CharacterSelection:
    character_id: UUID
    is_primary: bool = False
    role_name: str | None = None


@dataclass(frozen=True, slots=True)
class LorebookSelection:
    lorebook_id: UUID
    scope: Literal["all", "selected"] = "all"
    character_ids: tuple[UUID, ...] = ()
    role: Literal["main", "detail", "rule", "optional"] = "detail"
    priority: int = 0
    is_required: bool = True


@dataclass(frozen=True, slots=True)
class Composition:
    characters: tuple[CharacterSelection, ...] = ()
    lorebooks: tuple[LorebookSelection, ...] = ()


@dataclass(frozen=True, slots=True)
class Settings:
    model_id: UUID
    reasoning_effort: str
    start_entry_ids: tuple[UUID, ...]
    replacement_scope: Literal["same_family", "same_provider", "allowlist"] = (
        "same_family"
    )
    replacement_model_ids: tuple[UUID, ...] = ()
    unavailable_policy: Literal["pause", "use_original_until_shutdown"] = "pause"


@dataclass(frozen=True, slots=True)
class ReleasePublish:
    summary: str
    body: str
    auto_apply_media: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    snapshot_id: UUID
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str


@dataclass(frozen=True, slots=True)
class StartOptionInfo:
    id: UUID
    title: str


@dataclass(frozen=True, slots=True)
class PublishedProductInfo:
    product_id: UUID
    snapshot_id: UUID
    version: int
    title: str
    description: str | None
    start_options: list[StartOptionInfo]
    model_notice: ModelNotice | None


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    snapshot_id: UUID
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class PendingUpdatesInfo:
    current_snapshot_id: UUID
    current_expires_at: datetime | None
    expiry_reason: str | None
    latest_snapshot_id: UUID | None
    updates: list[UpdateInfo]
    model_notice: ModelNotice | None


@dataclass(frozen=True, slots=True)
class VersionAvailabilityInfo:
    snapshot_id: UUID
    expires_at: datetime | None
    expiry_reason: str | None
    model_notice: ModelNotice | None


@dataclass(frozen=True, slots=True)
class RevenueInfo:
    sales: str
    refunds: str
    net: str
    sale_count: int
    refund_count: int


@dataclass(frozen=True, slots=True)
class StatisticsMetrics:
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
    revenue: dict[str, RevenueInfo]


@dataclass(frozen=True, slots=True)
class StatisticsDayInfo(StatisticsMetrics):
    day: date
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StatisticsInfo:
    product_id: UUID
    snapshot_id: UUID | None
    timezone: str
    date_from: date
    date_to: date
    totals: StatisticsMetrics
    pending_days: list[date]
    days: list[StatisticsDayInfo]
