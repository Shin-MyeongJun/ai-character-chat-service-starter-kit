# 사용자 메시지 요청은 extra 필드를 거부한다. expected_revision은 마지막 메시지 동시 편집 충돌 검사값이다.
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateMessageRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=200000)


class ReplaceMessageRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=200000)
    expected_revision: int = Field(ge=1, strict=True)


class MessageResponseDto(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_type: str
    content: str
    position: int
    revision: int
    created_at: datetime
    character_id: UUID | None
    product_character_id: UUID | None
    product_snapshot_id: UUID | None
    generation_id: UUID | None
    generated_by_ai: bool
    model_id: UUID | None


class MessagePageResponseDto(BaseModel):
    items: list[MessageResponseDto]
    next_cursor: str | None


class RewindMessagesResponseDto(BaseModel):
    deleted_count: int
