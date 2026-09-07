from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, TypeAlias, TypeVar
from uuid import UUID

# Shared value types

CharacterVisibilityValue: TypeAlias = Literal["private", "public", "unlisted"]
CharacterStatusValue: TypeAlias = Literal["draft", "approved", "rejected"]
CharacterAssetTypeValue: TypeAlias = Literal["image", "audio", "video"]


# Commands
# Application service inputs. These are converted from router schemas.

@dataclass(frozen=True, slots=True)
class CharacterCreate:
    owner_id: UUID
    name: str
    persona_prompt: str
    description: str | None = None
    visibility: CharacterVisibilityValue = "private"
    status: CharacterStatusValue = "draft"
    default_model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CharacterUpdate:
    character_id: UUID
    owner_id: UUID
    name: str
    persona_prompt: str
    description: str | None
    visibility: CharacterVisibilityValue
    default_model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CharacterStatusChange:
    character_id: UUID
    owner_id: UUID
    status: CharacterStatusValue


@dataclass(frozen=True, slots=True)
class CharacterDelete:
    character_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CharacterImageCreate:
    character_id: UUID
    owner_id: UUID
    emotion_tag: str
    image_url: str
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class CharacterImageDefaultSet:
    character_id: UUID
    image_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CharacterImageDelete:
    character_id: UUID
    image_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CharacterAssetCreate:
    character_id: UUID
    owner_id: UUID
    asset_type: CharacterAssetTypeValue
    purpose: str
    file_url: str


@dataclass(frozen=True, slots=True)
class CharacterAssetDelete:
    character_id: UUID
    asset_id: UUID
    owner_id: UUID


# Results
# Application service outputs. Router schemas are built from these.

@dataclass(frozen=True, slots=True)
class CharacterInfo:
    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    persona_prompt: str
    visibility: CharacterVisibilityValue
    status: CharacterStatusValue
    default_model_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CharacterImageInfo:
    id: UUID
    character_id: UUID
    emotion_tag: str
    image_url: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CharacterAssetInfo:
    id: UUID
    character_id: UUID
    asset_type: CharacterAssetTypeValue
    purpose: str
    file_url: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CharacterPromptInfo:
    character_id: UUID
    persona_prompt: str
    # The chat caller can apply its own model override when this is None.
    default_model_id: UUID | None


@dataclass(frozen=True, slots=True)
class CharacterPromotionInfo:
    # Presentation data only; persona_prompt is intentionally not part of this result.
    character_id: UUID
    name: str
    description: str | None
    images: list[CharacterImageInfo]
    assets: list[CharacterAssetInfo]


@dataclass(frozen=True, slots=True)
class CharacterCursor:
    created_at: datetime
    id: UUID


TCharacterPageItem = TypeVar("TCharacterPageItem")


@dataclass(frozen=True, slots=True)
class CharacterPage(Generic[TCharacterPageItem]):
    items: list[TCharacterPageItem]
    next_cursor: CharacterCursor | None
