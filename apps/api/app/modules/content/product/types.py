from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.modules.content.character.types import CharacterSnapshotInfo
from app.modules.content.lorebook.types import LorebookSnapshotInfo
from app.modules.llm.types import ModelNoticeView

Visibility = Literal["private", "public", "unlisted"]


@dataclass(frozen=True, slots=True)
class ProductProfileCommand:
    title: str
    description: str | None = None
    opening_message: str | None = None
    visibility: Visibility = "private"


@dataclass(frozen=True, slots=True)
class ProductPaginationCommand:
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ProductStatisticsRangeCommand:
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
class ProductCompositionInfo:
    characters: tuple[CharacterSelection, ...] = ()
    lorebooks: tuple[LorebookSelection, ...] = ()


@dataclass(frozen=True, slots=True)
class ProductSettingsInfo:
    model_id: UUID
    reasoning_effort: str
    start_entry_ids: tuple[UUID, ...]
    replacement_scope: Literal["same_family", "same_provider", "allowlist"] = (
        "same_family"
    )
    replacement_model_ids: tuple[UUID, ...] = ()
    unavailable_policy: Literal["pause", "use_original_until_shutdown"] = "pause"


@dataclass(frozen=True, slots=True)
class ReleaseNoteCommand:
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
class PublishedProductView:
    product_id: UUID
    snapshot_id: UUID
    version: int
    title: str
    description: str | None
    start_options: list[StartOptionInfo]
    model_notice: ModelNoticeView | None


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
class PendingUpdatesView:
    current_snapshot_id: UUID
    current_expires_at: datetime | None
    expiry_reason: str | None
    latest_snapshot_id: UUID | None
    updates: list[UpdateInfo]
    model_notice: ModelNoticeView | None


@dataclass(frozen=True, slots=True)
class VersionAvailabilityView:
    snapshot_id: UUID
    expires_at: datetime | None
    expiry_reason: str | None
    model_notice: ModelNoticeView | None


@dataclass(frozen=True, slots=True)
class RevenueInfo:
    sales: str
    refunds: str
    net: str
    sale_count: int
    refund_count: int


@dataclass(frozen=True, slots=True)
class StatisticsMetricsInfo:
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
class StatisticsDayInfo(StatisticsMetricsInfo):
    day: date
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StatisticsInfo:
    product_id: UUID
    snapshot_id: UUID | None
    timezone: str
    date_from: date
    date_to: date
    totals: StatisticsMetricsInfo
    pending_days: list[date]
    days: list[StatisticsDayInfo]


@dataclass(frozen=True, slots=True)
class ProductStateInfo(ProductInfo):
    owner_id: UUID
    default_model_id: UUID | None
    reasoning_effort: str | None
    replacement_policy: dict
    latest_snapshot_id: UUID | None


@dataclass(frozen=True, slots=True)
class ProductSnapshotInfo:
    id: UUID
    product_id: UUID | None
    version: int
    snapshot_data: dict
    expires_at: datetime | None
    expiry_reason: str | None


@dataclass(frozen=True, slots=True)
class OwnedProductCommand:
    product_id: UUID
    owner_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True)
class ProductSnapshotCommand:
    snapshot_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True)
class ChangeSnapshotExpiryCommand:
    snapshot_id: UUID
    actor_id: UUID
    expires_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class ChangeProductStatusCommand:
    product_id: UUID
    actor_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class ProductStartSetInfo:
    id: UUID
    product_id: UUID
    lorebook_id: UUID
    entry_id: UUID
    sort_order: int


@dataclass(frozen=True, slots=True)
class ProductCharacterLinkInfo:
    id: UUID
    character_id: UUID
    role_order: int
    role_name: str | None
    is_primary: bool


@dataclass(frozen=True, slots=True)
class ProductLorebookLinkInfo:
    id: UUID
    lorebook_id: UUID
    role: str
    priority: int
    is_required: bool
    scope: str


@dataclass(frozen=True, slots=True)
class ProductLorebookTargetInfo:
    product_character_id: UUID
    product_lorebook_id: UUID


@dataclass(frozen=True, slots=True)
class ProductCompositionStateInfo:
    characters: list[ProductCharacterLinkInfo]
    books: list[ProductLorebookLinkInfo]
    targets: list[ProductLorebookTargetInfo]


@dataclass(frozen=True, slots=True)
class ReleaseNoteInfo:
    summary: str
    body: str
    change_kind: str
    update_policy: str


@dataclass(frozen=True, slots=True)
class SnapshotCharacterInfo:
    id: UUID
    character_snapshot_id: UUID
    role_order: int
    role_name: str | None
    is_primary: bool


@dataclass(frozen=True, slots=True)
class SnapshotLorebookInfo:
    id: UUID
    lorebook_snapshot_id: UUID
    role: str
    priority: int
    is_required: bool
    scope: str


@dataclass(frozen=True, slots=True)
class SnapshotStartInfo:
    id: UUID
    source_entry_id: UUID
    title: str | None
    content: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class SnapshotCompositionInfo:
    characters: list[SnapshotCharacterInfo]
    books: list[SnapshotLorebookInfo]
    targets: list[ProductLorebookTargetInfo]
    starts: list[SnapshotStartInfo]


@dataclass(frozen=True, slots=True)
class SnapshotRuntimeView:
    composition: SnapshotCompositionInfo
    characters: dict[UUID, CharacterSnapshotInfo]
    lorebooks: dict[UUID, LorebookSnapshotInfo]


@dataclass(frozen=True, slots=True)
class StatisticsBuildInfo:
    metrics: dict
    total: dict
    users: list[tuple]
    unique_users: set[UUID]


@dataclass(frozen=True, slots=True)
class StatisticsWorkInfo:
    product_id: UUID
    day: date


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateProductCommand:
    owner_id: UUID
    value: ProductProfileCommand


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateProductCommand:
    product_id: UUID
    owner_id: UUID
    value: ProductProfileCommand


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteProductCommand:
    product_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplaceCompositionCommand:
    product_id: UUID
    owner_id: UUID
    value: ProductCompositionInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCompositionCommand:
    product_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PublishedProductCommand:
    product_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PendingUpdatesCommand:
    conversation_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class VersionAvailabilityCommand:
    product_id: UUID
    snapshot_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildPublicationCommand:
    product_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProductCommand:
    product_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProductsCommand:
    owner_id: UUID
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAccessibleProductCommand:
    product_id: UUID
    user_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ListProductReleasesCommand:
    product_id: UUID
    after_version: int
    through_version: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProductStateCommand:
    product_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class EnsureAvailableCommand:
    snapshot_id: UUID
    now: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PublishCommand:
    product_id: UUID
    owner_id: UUID
    value: ReleaseNoteCommand


@dataclass(frozen=True, slots=True, kw_only=True)
class CorrectNoteCommand:
    product_id: UUID
    snapshot_id: UUID
    owner_id: UUID
    summary: str
    body: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SetSettingsCommand:
    product_id: UUID
    owner_id: UUID
    value: ProductSettingsInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaIsReferencedCommand:
    url: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RebuildDayCommand:
    product_id: UUID
    day: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessPendingCommand:
    limit: int = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class EnqueueRecentCommand:
    days: int = 7
    now: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetStatisticsCommand:
    product_id: UUID
    owner_id: UUID
    date_from: date
    date_to: date
    snapshot_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class MarkStatisticsDirtyCommand:
    product_id: UUID
    instant: datetime


@dataclass(frozen=True, slots=True)
class ProcessedStatisticsInfo:
    processed: int


@dataclass(frozen=True, slots=True)
class MediaReferenceView:
    referenced: bool
