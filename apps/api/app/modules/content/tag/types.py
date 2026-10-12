"""Public dictionary commands and immutable tag values."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TagInfo:
    id: UUID
    name: str
    description: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class GetTagCommand:
    tag_id: UUID


@dataclass(frozen=True, slots=True)
class AdminGetTagCommand:
    tag_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class GetTagByNameCommand:
    name: str


@dataclass(frozen=True, slots=True)
class GetTagsCommand:
    tag_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ResolveTagsCommand:
    names: tuple[str, ...]
    retained_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class CreateTagCommand:
    actor_id: UUID
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateTagCommand:
    tag_id: UUID
    actor_id: UUID
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DeactivateTagCommand:
    tag_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class PublicTagLinkInfo:
    tag_id: UUID
    sort_order: int
    assigned_by: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InternalTagLinkInfo:
    tag_id: UUID
    source: str
    assigned_by: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PublicTagInfo:
    id: UUID
    name: str
    is_active: bool
    sort_order: int


@dataclass(frozen=True, slots=True)
class InternalTagInfo:
    id: UUID
    name: str
    is_active: bool
    source: str
    assigned_by: UUID | None
    created_at: datetime
    updated_at: datetime
