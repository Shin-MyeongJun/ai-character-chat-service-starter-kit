from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, TypeAlias, TypeVar
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
class LorebookCreate:
    owner_id: UUID
    title: str
    description: str | None = None
    visibility: LorebookVisibilityValue = "private"
    status: LorebookStatusValue = "draft"


@dataclass(frozen=True, slots=True)
class LorebookUpdate:
    lorebook_id: UUID
    owner_id: UUID
    title: str
    description: str | None
    visibility: LorebookVisibilityValue


@dataclass(frozen=True, slots=True)
class LorebookStatusChange:
    lorebook_id: UUID
    owner_id: UUID
    status: LorebookStatusValue


@dataclass(frozen=True, slots=True)
class LorebookDelete:
    lorebook_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class LorebookEntryCreate:
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
class LorebookEntryUpdate:
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
class LorebookEntryDelete:
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
class ActiveLorebookEntry:
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
