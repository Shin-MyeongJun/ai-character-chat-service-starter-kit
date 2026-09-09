from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: UUID
    start_set_id: UUID | None = None


class SwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_snapshot_id: UUID


class ConversationStartedResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_snapshot_id: UUID
    start_set_id: UUID


class VersionSwitchedResponseDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    snapshot_id: UUID
    changed: bool
