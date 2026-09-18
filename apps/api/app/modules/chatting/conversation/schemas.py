# start_set_id=None은 시작 항목이 정확히 하나일 때만 자동 선택된다. changed=False는 동일 버전 재요청 결과다.
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.http.schemas import ModelNoticeResponseDto, ResponseDto


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


class UpdateInfoResponseDto(ResponseDto):
    snapshot_id: UUID
    version: int
    summary: str
    body: str
    change_kind: str
    update_policy: str
    expires_at: datetime | None


class PendingUpdatesInfoResponseDto(ResponseDto):
    current_snapshot_id: UUID
    current_expires_at: datetime | None
    expiry_reason: str | None
    latest_snapshot_id: UUID | None
    updates: list[UpdateInfoResponseDto]
    model_notice: ModelNoticeResponseDto | None
