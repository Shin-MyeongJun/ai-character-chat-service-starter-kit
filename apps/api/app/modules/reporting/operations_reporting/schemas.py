"""Read-only administrator prompt HTTP contract; request_json exists only in detail."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ListGenerationPromptsRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date
    date_to: date
    conversation_id: UUID | None = None
    status: Literal["pending", "succeeded", "failed", "cancelled", "stale"] | None = (
        None
    )
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)


class GenerationPromptSummaryResponseDto(BaseModel):
    generation_id: UUID
    conversation_id: UUID
    model_id: UUID
    model_name: str
    reasoning_effort: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    history_invalidated_at: datetime | None
    prompt_recorded: bool
    prompt_created_at: datetime | None
    provider: str | None


class GenerationPromptResponseDto(BaseModel):
    request_json: str
    digest: str
    format_version: int
    created_at: datetime
    provider: str
    max_output_tokens: int


class GenerationPromptPageResponseDto(BaseModel):
    items: list[GenerationPromptSummaryResponseDto]
    total: int
    page: int
    page_size: int


class GenerationPromptDetailResponseDto(BaseModel):
    generation: GenerationPromptSummaryResponseDto
    prompt: GenerationPromptResponseDto | None
