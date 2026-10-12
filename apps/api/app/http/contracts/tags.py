"""Shared HTTP values, independent of content module implementations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TagsRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[str]


class PublicTagResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    is_active: bool
    sort_order: int


class InternalTagResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    is_active: bool
    source: str
    assigned_by: UUID | None
    created_at: datetime
    updated_at: datetime


class TagWriteRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None


class TagResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    is_active: bool
