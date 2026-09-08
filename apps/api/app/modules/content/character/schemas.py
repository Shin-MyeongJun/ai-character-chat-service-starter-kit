from datetime import datetime
from typing import Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CharacterVisibilityDto: TypeAlias = Literal["private", "public", "unlisted"]
CharacterStatusDto: TypeAlias = Literal["draft", "approved", "rejected"]
CharacterAssetTypeDto: TypeAlias = Literal["image", "audio", "video"]


# Requests


class CreateCharacterRequestDto(BaseModel):
    name: str = Field(min_length=1)
    persona_prompt: str = Field(min_length=1)
    description: str | None = None
    visibility: CharacterVisibilityDto = "private"
    default_model_id: UUID | None = None


class UpdateCharacterRequestDto(BaseModel):
    character_id: UUID
    name: str = Field(min_length=1)
    persona_prompt: str = Field(min_length=1)
    description: str | None
    visibility: CharacterVisibilityDto
    default_model_id: UUID | None = None


class ChangeCharacterStatusRequestDto(BaseModel):
    character_id: UUID
    status: CharacterStatusDto


class DeleteCharacterRequestDto(BaseModel):
    character_id: UUID


class GetCharacterByIdRequestDto(BaseModel):
    character_id: UUID


class ListCharactersRequestDto(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None

    @model_validator(mode="after")
    def validate_cursor(self) -> Self:
        # TODO: Map cursor validation failures to unified API error codes.
        if (self.cursor_created_at is None) != (self.cursor_id is None):
            raise ValueError(
                "cursor_created_at and cursor_id must be provided together."
            )
        if (
            self.cursor_created_at is not None
            and self.cursor_created_at.utcoffset() is None
        ):
            raise ValueError("cursor_created_at must include a timezone offset.")
        return self


class SearchCharactersByNameRequestDto(ListCharactersRequestDto):
    keyword: str = Field(min_length=1)


class AddCharacterImageRequestDto(BaseModel):
    character_id: UUID
    emotion_tag: str = Field(min_length=1)
    image_url: str = Field(min_length=1)
    is_default: bool = False


class ListCharacterImagesRequestDto(BaseModel):
    character_id: UUID


class SetDefaultCharacterImageRequestDto(BaseModel):
    character_id: UUID
    image_id: UUID


class DeleteCharacterImageRequestDto(BaseModel):
    character_id: UUID
    image_id: UUID


class AddCharacterAssetRequestDto(BaseModel):
    character_id: UUID
    asset_type: CharacterAssetTypeDto
    purpose: str = Field(min_length=1)
    file_url: str = Field(min_length=1)


class ListCharacterAssetsRequestDto(BaseModel):
    character_id: UUID


class ListCharacterAssetsByTypeRequestDto(BaseModel):
    character_id: UUID
    asset_type: CharacterAssetTypeDto


class DeleteCharacterAssetRequestDto(BaseModel):
    character_id: UUID
    asset_id: UUID


# Responses


class CharacterResponseDto(BaseModel):
    id: UUID
    owner_id: UUID
    name: str
    description: str | None = None
    persona_prompt: str
    visibility: CharacterVisibilityDto
    status: CharacterStatusDto
    default_model_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CharacterImageResponseDto(BaseModel):
    id: UUID
    character_id: UUID
    emotion_tag: str
    image_url: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CharacterAssetResponseDto(BaseModel):
    id: UUID
    character_id: UUID
    asset_type: CharacterAssetTypeDto
    purpose: str
    file_url: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CharacterCursorResponseDto(BaseModel):
    created_at: datetime
    id: UUID

    model_config = ConfigDict(from_attributes=True)


class CreateCharacterResponseDto(BaseModel):
    character: CharacterResponseDto


class UpdateCharacterResponseDto(BaseModel):
    character: CharacterResponseDto


class ChangeCharacterStatusResponseDto(BaseModel):
    character: CharacterResponseDto


class DeleteCharacterResponseDto(BaseModel):
    deleted: bool


class GetCharacterByIdResponseDto(BaseModel):
    character: CharacterResponseDto


class ListCharactersResponseDto(BaseModel):
    characters: list[CharacterResponseDto]
    next_cursor: CharacterCursorResponseDto | None = None


class SearchCharactersByNameResponseDto(BaseModel):
    characters: list[CharacterResponseDto]
    next_cursor: CharacterCursorResponseDto | None = None


class AddCharacterImageResponseDto(BaseModel):
    image: CharacterImageResponseDto


class ListCharacterImagesResponseDto(BaseModel):
    images: list[CharacterImageResponseDto]


class SetDefaultCharacterImageResponseDto(BaseModel):
    image: CharacterImageResponseDto


class DeleteCharacterImageResponseDto(BaseModel):
    deleted: bool


class AddCharacterAssetResponseDto(BaseModel):
    asset: CharacterAssetResponseDto


class ListCharacterAssetsResponseDto(BaseModel):
    assets: list[CharacterAssetResponseDto]


class ListCharacterAssetsByTypeResponseDto(BaseModel):
    assets: list[CharacterAssetResponseDto]


class DeleteCharacterAssetResponseDto(BaseModel):
    deleted: bool
