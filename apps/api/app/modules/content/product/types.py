from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

Visibility = Literal["private", "public", "unlisted"]


@dataclass(frozen=True, slots=True)
class ProductWrite:
    title: str
    description: str | None = None
    opening_message: str | None = None
    visibility: Visibility = "private"


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
