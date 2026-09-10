from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.http.contracts import character, lorebook


class ExpiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expires_at: datetime | None
    reason: str = Field(min_length=1, max_length=2000)


class StatusRequest(BaseModel):
    status: Literal["draft", "approved", "rejected"]


class RetirementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    announced_at: datetime
    shutdown_at: datetime


class ExpiryChangedResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_id: UUID
    expires_at: datetime | None
    reason: str


__all__ = ["character", "lorebook"]
