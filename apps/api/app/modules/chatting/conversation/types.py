# product_snapshot_id=None은 버전 매핑이 검증되지 않은 legacy 대화다. initial_snapshot_id는 최초 생성 통계 기준이다.
# history_revision은 원문 교체·삭제 세대이며 단순 append와 상품 버전 전환에서는 증가하지 않는다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.llm.types import ExecutionView


@dataclass(frozen=True, slots=True)
class ConversationStartedInfo:
    id: UUID
    product_snapshot_id: UUID
    start_set_id: UUID


@dataclass(frozen=True, slots=True)
class PreparedConversationInfo:
    conversation: ConversationStartedInfo
    opening_message: str
    product_character_id: UUID


@dataclass(frozen=True, slots=True)
class ConversationCharacterInfo:
    character_id: UUID | None
    product_character_id: UUID | None
    role_order: int


@dataclass(frozen=True, slots=True)
class VersionSwitchedInfo:
    snapshot_id: UUID
    changed: bool


@dataclass(frozen=True, slots=True)
class RuntimeStart:
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class RuntimeCharacter:
    id: str
    snapshot_id: str
    primary: bool
    data: dict


@dataclass(frozen=True, slots=True)
class RuntimeLorebook:
    id: str
    scope: str
    targets: list[str]
    entries: list[dict]


@dataclass(frozen=True, slots=True)
class ConversationRuntimeView:
    execution: ExecutionView
    product_snapshot_id: str
    settings: dict
    start: RuntimeStart
    characters: list[RuntimeCharacter]
    lorebooks: list[RuntimeLorebook]


@dataclass(frozen=True, slots=True)
class ConversationInfo:
    id: UUID
    user_id: UUID
    product_id: UUID
    product_snapshot_id: UUID | None
    initial_snapshot_id: UUID | None
    start_set_id: UUID | None
    created_at: datetime
    history_revision: int = 1


@dataclass(frozen=True, slots=True)
class ConversationCharacterCommand:
    character_id: UUID | None
    product_character_id: UUID
    role_order: int


@dataclass(frozen=True, slots=True)
class CreateConversationCommand:
    user_id: UUID
    product_id: UUID
    snapshot_id: UUID
    start_set_id: UUID
    title: str
    opening_message: str
    primary_product_character_id: UUID
    characters: tuple[ConversationCharacterCommand, ...]


@dataclass(frozen=True, slots=True)
class GetStatisticsFactsCommand:
    product_id: UUID
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class ConversationStatisticsInfo:
    conversations: list[tuple]
    transitions: list[tuple]


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnedConversationCommand:
    conversation_id: UUID
    user_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvanceHistoryRevisionCommand:
    conversation_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class StartConversationCommand:
    product_id: UUID
    user_id: UUID
    start_set_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareRuntimeContextCommand:
    conversation_id: UUID
    user_id: UUID
    activation_text: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchVersionCommand:
    conversation_id: UUID
    user_id: UUID
    target_snapshot_id: UUID
    automatic: bool = False
