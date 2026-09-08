from datetime import datetime
from typing import Annotated, Literal, Self, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.content.lorebook import constraints

LorebookVisibilityDto: TypeAlias = Literal["private", "public", "unlisted"]
LorebookStatusDto: TypeAlias = Literal["draft", "approved", "rejected"]
LorebookEntryTypeDto: TypeAlias = Literal[
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
]
LorebookEntryActivationTypeDto: TypeAlias = Literal[
    "always", "keyword", "semantic", "manual"
]
LorebookEntryMatchModeDto: TypeAlias = Literal["exact", "contains", "regex"]
LorebookEntryPlacementDto: TypeAlias = Literal[
    "system_top",
    "before_memory",
    "after_memory",
    "before_history",
    "near_user_message",
]

TriggerDto = Annotated[
    str,
    Field(min_length=1, max_length=constraints.ENTRY_TRIGGER_MAX_LENGTH),
]


class CreateLorebookRequestDto(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=constraints.LOREBOOK_TITLE_MAX_LENGTH,
    )
    description: str | None = Field(
        default=None,
        max_length=constraints.LOREBOOK_DESCRIPTION_MAX_LENGTH,
    )
    visibility: LorebookVisibilityDto = "private"


class UpdateLorebookRequestDto(BaseModel):
    lorebook_id: UUID
    title: str = Field(
        min_length=1,
        max_length=constraints.LOREBOOK_TITLE_MAX_LENGTH,
    )
    description: str | None = Field(
        max_length=constraints.LOREBOOK_DESCRIPTION_MAX_LENGTH
    )
    visibility: LorebookVisibilityDto


class ChangeLorebookStatusRequestDto(BaseModel):
    lorebook_id: UUID
    status: LorebookStatusDto


class DeleteLorebookRequestDto(BaseModel):
    lorebook_id: UUID


class CursorRequestDto(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None

    @model_validator(mode="after")
    def validate_cursor(self) -> Self:
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


class ListLorebooksRequestDto(CursorRequestDto):
    pass


class CreateLorebookEntryRequestDto(BaseModel):
    lorebook_id: UUID
    title: str | None = Field(
        default=None,
        max_length=constraints.ENTRY_TITLE_MAX_LENGTH,
    )
    content: str = Field(
        min_length=1,
        max_length=constraints.ENTRY_CONTENT_MAX_LENGTH,
    )
    entry_type: LorebookEntryTypeDto = "world"
    activation_type: LorebookEntryActivationTypeDto = "always"
    key_triggers: list[TriggerDto] | None = Field(
        default=None,
        max_length=constraints.ENTRY_TRIGGER_MAX_COUNT,
    )
    match_mode: LorebookEntryMatchModeDto = "contains"
    priority: int = Field(
        default=0,
        ge=constraints.POSTGRES_INTEGER_MIN,
        le=constraints.POSTGRES_INTEGER_MAX,
    )
    token_budget: int | None = Field(
        default=None,
        ge=0,
        le=constraints.POSTGRES_INTEGER_MAX,
    )
    placement: LorebookEntryPlacementDto = "before_history"
    is_enabled: bool = True
    metadata: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_keyword_triggers(self) -> Self:
        if (
            self.activation_type == "keyword"
            and self.is_enabled
            and not self.key_triggers
        ):
            raise ValueError("Keyword entries require at least one trigger.")
        return self


class UpdateLorebookEntryRequestDto(BaseModel):
    lorebook_id: UUID
    entry_id: UUID
    title: str | None = Field(max_length=constraints.ENTRY_TITLE_MAX_LENGTH)
    content: str = Field(
        min_length=1,
        max_length=constraints.ENTRY_CONTENT_MAX_LENGTH,
    )
    entry_type: LorebookEntryTypeDto
    activation_type: LorebookEntryActivationTypeDto
    key_triggers: list[TriggerDto] | None = Field(
        max_length=constraints.ENTRY_TRIGGER_MAX_COUNT
    )
    match_mode: LorebookEntryMatchModeDto
    priority: int = Field(
        ge=constraints.POSTGRES_INTEGER_MIN,
        le=constraints.POSTGRES_INTEGER_MAX,
    )
    token_budget: int | None = Field(
        ge=0,
        le=constraints.POSTGRES_INTEGER_MAX,
    )
    placement: LorebookEntryPlacementDto
    is_enabled: bool
    metadata: dict[str, object] | None

    @model_validator(mode="after")
    def validate_keyword_triggers(self) -> Self:
        if (
            self.activation_type == "keyword"
            and self.is_enabled
            and not self.key_triggers
        ):
            raise ValueError("Keyword entries require at least one trigger.")
        return self


class DeleteLorebookEntryRequestDto(BaseModel):
    lorebook_id: UUID
    entry_id: UUID


class ListLorebookEntriesRequestDto(CursorRequestDto):
    pass


class LorebookResponseDto(BaseModel):
    id: UUID
    owner_id: UUID
    title: str
    description: str | None = None
    visibility: LorebookVisibilityDto
    status: LorebookStatusDto
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LorebookEntryResponseDto(BaseModel):
    id: UUID
    lorebook_id: UUID
    title: str | None = None
    content: str
    entry_type: LorebookEntryTypeDto
    activation_type: LorebookEntryActivationTypeDto
    key_triggers: list[str] | None = None
    match_mode: LorebookEntryMatchModeDto
    priority: int
    token_budget: int | None = None
    placement: LorebookEntryPlacementDto
    is_enabled: bool
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LorebookCursorResponseDto(BaseModel):
    created_at: datetime
    id: UUID


class CreateLorebookResponseDto(BaseModel):
    lorebook: LorebookResponseDto


class UpdateLorebookResponseDto(BaseModel):
    lorebook: LorebookResponseDto


class ChangeLorebookStatusResponseDto(BaseModel):
    lorebook: LorebookResponseDto


class DeleteLorebookResponseDto(BaseModel):
    deleted: bool


class GetLorebookByIdResponseDto(BaseModel):
    lorebook: LorebookResponseDto


class ListLorebooksResponseDto(BaseModel):
    lorebooks: list[LorebookResponseDto]
    next_cursor: LorebookCursorResponseDto | None = None


class CreateLorebookEntryResponseDto(BaseModel):
    entry: LorebookEntryResponseDto


class UpdateLorebookEntryResponseDto(BaseModel):
    entry: LorebookEntryResponseDto


class DeleteLorebookEntryResponseDto(BaseModel):
    deleted: bool


class GetLorebookEntryResponseDto(BaseModel):
    entry: LorebookEntryResponseDto


class ListLorebookEntriesResponseDto(BaseModel):
    entries: list[LorebookEntryResponseDto]
    next_cursor: LorebookCursorResponseDto | None = None
