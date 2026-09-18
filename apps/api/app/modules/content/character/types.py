# CharacterSnapshotInfo.character_id=None은 원본 삭제 후에도 남은 복사본이다. snapshot id와 원본 id는 별개다.
# CharacterMediaInfo.size_bytes는 바이트 수, binding=None은 아직 연결한 이력이 없는 업로드다.
# state는 pending(예약), ready(저장 확인), deleting(정리 중), deleted(정리 완료)로 사용한다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Generic, Literal, TypeAlias, TypeVar
from uuid import UUID

# Shared value types

CharacterVisibilityValue: TypeAlias = Literal["private", "public", "unlisted"]
CharacterStatusValue: TypeAlias = Literal["draft", "approved", "rejected"]
CharacterAssetTypeValue: TypeAlias = Literal["image", "audio", "video"]


# Commands
# Application service inputs. These are converted from router schemas.


@dataclass(frozen=True, slots=True)
class CreateCharacterCommand:
    owner_id: UUID
    name: str
    persona_prompt: str
    description: str | None = None
    visibility: CharacterVisibilityValue = "private"
    status: CharacterStatusValue = "draft"
    default_model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UpdateCharacterCommand:
    character_id: UUID
    owner_id: UUID
    name: str
    persona_prompt: str
    description: str | None
    visibility: CharacterVisibilityValue
    default_model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ChangeCharacterStatusCommand:
    character_id: UUID
    owner_id: UUID
    status: CharacterStatusValue


@dataclass(frozen=True, slots=True)
class DeleteCharacterCommand:
    character_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CreateCharacterImageCommand:
    character_id: UUID
    owner_id: UUID
    emotion_tag: str
    image_url: str
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class SetDefaultCharacterImageCommand:
    character_id: UUID
    image_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class DeleteCharacterImageCommand:
    character_id: UUID
    image_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CreateCharacterAssetCommand:
    character_id: UUID
    owner_id: UUID
    asset_type: CharacterAssetTypeValue
    purpose: str
    file_url: str


@dataclass(frozen=True, slots=True)
class DeleteCharacterAssetCommand:
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCharactersCommand:
    cursor: CharacterCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCharactersByOwnerIdCommand:
    owner_id: UUID
    cursor: CharacterCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterByIdCommand:
    character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterByIdAndOwnerIdCommand:
    character_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterImageCommand:
    character_id: UUID
    image_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterImageByEmotionTagCommand:
    character_id: UUID
    emotion_tag: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetDefaultCharacterImageCommand:
    character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCharacterImagesCommand:
    character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterAssetCommand:
    character_id: UUID
    asset_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListCharacterAssetsCommand:
    character_id: UUID
    asset_type: CharacterAssetTypeValue | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterPromptCommand:
    character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCharacterPromotionCommand:
    character_id: UUID


@dataclass(frozen=True, slots=True)
class GetOwnedCharactersCommand:
    ids: tuple[UUID, ...]
    owner_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True)
class FreezeCharacterCommand:
    character_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class CharacterSnapshotInfo:
    id: UUID
    character_id: UUID | None
    version: int
    snapshot_data: dict


@dataclass(frozen=True, slots=True)
class GetSnapshotMediaCommand:
    snapshot_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class SnapshotMediaInfo:
    manifest: frozenset[tuple]


@dataclass(frozen=True, slots=True)
class CheckMediaReferenceCommand:
    url: str


@dataclass(frozen=True, slots=True)
class MediaReferenceInfo:
    referenced: bool


@dataclass(frozen=True, slots=True)
class GetCharacterSnapshotsCommand:
    snapshot_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class UploadCharacterMediaCommand:
    character_id: UUID
    owner_id: UUID
    request_id: UUID
    content: BinaryIO
    content_type: str
    original_filename: str
    purpose: str


@dataclass(frozen=True, slots=True)
class CharacterMediaInfo:
    id: UUID
    character_id: UUID
    owner_id: UUID
    request_id: UUID
    storage_kind: str
    storage_id: str
    object_key: str
    content_type: str
    size_bytes: int
    original_filename: str
    purpose: str
    sha256: str
    state: str
    binding: str | None
    updated_at: datetime

    @property
    def content_url(self) -> str:
        return f"/characters/media/{self.id}/content"


@dataclass(frozen=True, slots=True)
class ReadCharacterMediaCommand:
    media_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class ReadSnapshotMediaCommand:
    media_id: UUID
    snapshot_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class CleanupCharacterMediaCommand:
    media_id: UUID
    older_than: datetime


@dataclass(frozen=True, slots=True)
class CleanupCharacterMediaInfo:
    deleted: bool
    reason: str
