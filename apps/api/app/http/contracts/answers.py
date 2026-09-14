from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GenerateAnswerRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=128)
    input_message_id: UUID
    expected_revision: int = Field(ge=1)
    product_character_id: UUID


class GenerateAnswerResponseDto(BaseModel):
    generation_id: UUID
    status: str
    content: str | None
    model: str
    error_code: str | None
    retryable: bool
    uncertain: bool
