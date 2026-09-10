from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ModelNoticeResponseDto(ResponseDto):
    state: str
    reason: str | None = None
    model_id: UUID | None = None
    model_name: str | None = None
    announced_at: datetime | None = None
    shutdown_at: datetime | None = None
    transition_deadline: datetime | None = None
    replacement_model_id: UUID | None = None
    replacement_model_name: str | None = None
    replacement_reasoning_effort: str | None = None
    unavailable_policy: str | None = None
