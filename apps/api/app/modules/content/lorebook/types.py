# 문자열 길이 제한은 문자 수, ENTRY_METADATA_MAX_BYTES는 JSON 직렬화 바이트 수다.
# metadata=None은 저장 시 빈 객체가 된다. token_budget=None은 미지정이다.
# v1 옵션이 있는 스냅샷 항목은 UTF-8 바이트 추정 예산을 적용하고 기존 옵션 없는 항목은 이전 동작을 유지한다.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, NotRequired, TypeAlias, TypedDict, TypeVar
from uuid import UUID

LorebookVisibilityValue: TypeAlias = Literal["private", "public", "unlisted"]
LorebookStatusValue: TypeAlias = Literal["draft", "approved", "rejected"]
LorebookEntryTypeValue: TypeAlias = Literal[
    "author_note",
    "world",
    "genre",
    "rule",
    "location",
    "faction",
    "character_relation",
    "event",
    "term",
    "secret",
    "start_set",
]
LorebookEntryActivationTypeValue: TypeAlias = Literal[
    "always", "keyword", "semantic", "manual"
]
LorebookEntryMatchModeValue: TypeAlias = Literal["exact", "contains", "regex"]
LorebookEntryPlacementValue: TypeAlias = Literal[
    "system_top",
    "before_memory",
    "after_memory",
    "before_history",
    "near_user_message",
]


@dataclass(frozen=True, slots=True)
class CreateLorebookCommand:
    owner_id: UUID
    title: str
    description: str | None = None
    visibility: LorebookVisibilityValue = "private"
    status: LorebookStatusValue = "draft"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UpdateLorebookCommand:
    lorebook_id: UUID
    owner_id: UUID
    title: str
    description: str | None
    visibility: LorebookVisibilityValue


@dataclass(frozen=True, slots=True)
class ChangeLorebookStatusCommand:
    lorebook_id: UUID
    owner_id: UUID
    status: LorebookStatusValue


@dataclass(frozen=True, slots=True)
class DeleteLorebookCommand:
    lorebook_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CreateLorebookEntryCommand:
    lorebook_id: UUID
    owner_id: UUID
    content: str
    title: str | None = None
    entry_type: LorebookEntryTypeValue = "world"
    activation_type: LorebookEntryActivationTypeValue = "always"
    key_triggers: list[str] | None = None
    match_mode: LorebookEntryMatchModeValue = "contains"
    priority: int = 0
    token_budget: int | None = None
    placement: LorebookEntryPlacementValue = "before_history"
    is_enabled: bool = True
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class UpdateLorebookEntryCommand:
    lorebook_id: UUID
    entry_id: UUID
    owner_id: UUID
    content: str
    title: str | None
    entry_type: LorebookEntryTypeValue
    activation_type: LorebookEntryActivationTypeValue
    key_triggers: list[str] | None
    match_mode: LorebookEntryMatchModeValue
    priority: int
    token_budget: int | None
    placement: LorebookEntryPlacementValue
    is_enabled: bool
    metadata: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class DeleteLorebookEntryCommand:
    lorebook_id: UUID
    entry_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class LorebookInfo:
    id: UUID
    owner_id: UUID
    title: str
    description: str | None
    visibility: LorebookVisibilityValue
    status: LorebookStatusValue
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class LorebookEntryInfo:
    id: UUID
    lorebook_id: UUID
    title: str | None
    content: str
    entry_type: LorebookEntryTypeValue
    activation_type: LorebookEntryActivationTypeValue
    key_triggers: list[str] | None
    match_mode: LorebookEntryMatchModeValue
    priority: int
    token_budget: int | None
    placement: LorebookEntryPlacementValue
    is_enabled: bool
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ActiveLorebookEntryInfo:
    entry_id: UUID
    lorebook_id: UUID
    title: str | None
    content: str
    entry_type: LorebookEntryTypeValue
    priority: int
    token_budget: int | None
    placement: LorebookEntryPlacementValue


@dataclass(frozen=True, slots=True)
class LorebookCursor:
    created_at: datetime
    id: UUID


TPageItem = TypeVar("TPageItem")


@dataclass(frozen=True, slots=True)
class LorebookPage(Generic[TPageItem]):
    items: list[TPageItem]
    next_cursor: LorebookCursor | None


@dataclass(frozen=True, slots=True)
class LorebookEntryPage(Generic[TPageItem]):
    items: list[TPageItem]
    next_cursor: LorebookCursor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ListLorebooksCommand:
    cursor: LorebookCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class ListLorebooksByOwnerIdCommand:
    owner_id: UUID
    cursor: LorebookCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLorebookByIdCommand:
    lorebook_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLorebookByIdAndOwnerIdCommand:
    lorebook_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListLorebookEntriesCommand:
    lorebook_id: UUID
    cursor: LorebookCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class ListLorebookEntriesByOwnerIdCommand:
    lorebook_id: UUID
    owner_id: UUID
    cursor: LorebookCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLorebookEntryCommand:
    lorebook_id: UUID
    entry_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLorebookEntryByOwnerIdCommand:
    lorebook_id: UUID
    entry_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAlwaysEntriesCommand:
    lorebook_ids: Sequence[UUID]


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivateKeywordEntriesCommand:
    lorebook_ids: Sequence[UUID]
    text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ListStartSetsCommand:
    lorebook_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class GetOwnedLorebooksCommand:
    ids: tuple[UUID, ...]
    owner_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True)
class GetStartEntriesCommand:
    ids: tuple[UUID, ...]
    lorebook_ids: tuple[UUID, ...] | None = None


@dataclass(frozen=True, slots=True)
class FreezeLorebookCommand:
    lorebook_id: UUID
    owner_id: UUID


class LorebookActivationOptions(TypedDict):
    # The existing version equality check also accepts JSON number 1.0 and True.
    version: int | float
    match: Literal["any", "all"]
    scan_depth: int
    search_target: Literal["all", "user"]
    partial_match: bool
    case_sensitive: bool
    order: int
    exclusive_group: str


class LorebookEntryCommandFields(TypedDict):
    """Entry fields passed to CreateLorebookEntryCommand, excluding IDs."""

    content: str
    title: NotRequired[str | None]
    entry_type: NotRequired[LorebookEntryTypeValue]
    activation_type: NotRequired[LorebookEntryActivationTypeValue]
    key_triggers: NotRequired[list[str] | None]
    match_mode: NotRequired[LorebookEntryMatchModeValue]
    priority: NotRequired[int]
    token_budget: NotRequired[int | None]
    placement: NotRequired[LorebookEntryPlacementValue]
    is_enabled: NotRequired[bool]
    metadata: NotRequired[dict[str, object] | None]


class LorebookSnapshotEntryData(TypedDict):
    """Runtime entry fields; legacy optional fields and extensions stay intact."""

    id: str
    content: str
    entry_type: LorebookEntryTypeValue
    activation_type: LorebookEntryActivationTypeValue
    is_enabled: bool
    match_mode: LorebookEntryMatchModeValue
    title: NotRequired[str | None]
    key_triggers: NotRequired[list[str] | None]
    priority: NotRequired[int]
    token_budget: NotRequired[int | None]
    placement: NotRequired[LorebookEntryPlacementValue]
    metadata: NotRequired[dict[str, object] | None]


class LorebookSnapshotData(TypedDict):
    entries: list[LorebookSnapshotEntryData]
    title: NotRequired[str]
    description: NotRequired[str | None]


LorebookActivationReason: TypeAlias = Literal[
    "included",
    "disabled",
    "start_scene",
    "manual_not_selected",
    "semantic_not_supported",
    "keyword_mismatch",
    "entry_budget_exceeded",
    "exclusive_group",
]


class LorebookEntryDiagnostic(TypedDict):
    id: str
    included: bool
    reason: LorebookActivationReason
    order: int | None
    estimated_tokens: int
    placement: LorebookEntryPlacementValue | None


@dataclass(frozen=True, slots=True)
class LorebookSnapshotInfo:
    id: UUID
    lorebook_id: UUID | None
    version: int
    snapshot_data: LorebookSnapshotData


@dataclass(frozen=True, slots=True)
class GetLorebookSnapshotsCommand:
    snapshot_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivateSnapshotEntriesCommand:
    snapshot: LorebookSnapshotInfo
    text: str = ""
    messages: tuple[tuple[str, str], ...] = ()
    manual_entry_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActivatedSnapshotEntriesInfo:
    entries: list[LorebookSnapshotEntryData]


@dataclass(frozen=True, slots=True)
class DiagnoseDraftEntriesCommand:
    owner_id: UUID
    entries: tuple[LorebookSnapshotEntryData, ...]
    messages: tuple[tuple[str, str], ...]
    manual_entry_ids: tuple[str, ...] = ()


LOREBOOK_TITLE_MAX_LENGTH = 200
LOREBOOK_DESCRIPTION_MAX_LENGTH = 4_000
ENTRY_TITLE_MAX_LENGTH = 200
ENTRY_CONTENT_MAX_LENGTH = 32_000
ENTRY_TRIGGER_MAX_COUNT = 64
ENTRY_TRIGGER_MAX_LENGTH = 256
ENTRY_METADATA_MAX_BYTES = 16_384

POSTGRES_INTEGER_MIN = -(2**31)
POSTGRES_INTEGER_MAX = 2**31 - 1


@dataclass(frozen=True, slots=True)
class PublicTagsCommand:
    target_id: UUID
    user_id: UUID
    names: tuple[str, ...] = ()
    tag_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InternalTagsCommand:
    target_id: UUID
    actor_id: UUID
    names: tuple[str, ...] = ()
    tag_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SystemTagsCommand:
    target_id: UUID
    names: tuple[str, ...] = ()
    tag_id: UUID | None = None
