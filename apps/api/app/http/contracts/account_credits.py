"""Owner credit history HTTP values; payment and internal idempotency data stay private."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class CreditHistoryRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=50, ge=1, le=100)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    cursor_created_at: AwareDatetime | None = None
    cursor_id: UUID | None = None
    direction: Literal["usage", "acquisition"] | None = None

    @model_validator(mode="after")
    def validate_history_filters(self) -> Self:
        if (self.cursor_id is None) != (self.cursor_created_at is None):
            raise ValueError("Both cursor values are required.")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("History range must be non-empty.")
        return self


class CreditTransactionResponseDto(BaseModel):
    id: UUID
    operation: str
    amount: int
    free_amount: int | None
    paid_amount: int | None
    created_at: datetime


class CreditHistoryResponseDto(BaseModel):
    items: list[CreditTransactionResponseDto]
    next_cursor_created_at: datetime | None = None
    next_cursor_id: UUID | None = None
