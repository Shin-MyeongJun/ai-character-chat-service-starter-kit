from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.modules.llm.types import ExecutionView


@dataclass(frozen=True, slots=True)
class GeneratedMessage:
    product_character_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class GenerationResult:
    input_tokens: int
    output_tokens: int
    cost_credit: int
    messages: tuple[GeneratedMessage, ...] = ()
    outcome: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ConversationStartedInfo:
    id: UUID
    product_snapshot_id: UUID
    start_set_id: UUID


@dataclass(frozen=True, slots=True)
class VersionSwitchedInfo:
    snapshot_id: UUID
    changed: bool


@dataclass(frozen=True, slots=True)
class GenerationInfo:
    id: UUID
    created: bool
    status: str
    product_snapshot_id: UUID
    model_id: UUID
    model_name: str
    reasoning_effort: str
    message_count: int


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
class ConversationStart:
    product_id: UUID
    start_set_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class VersionSwitch:
    target_snapshot_id: UUID


@dataclass(frozen=True, slots=True)
class ConversationInfo:
    id: UUID
    user_id: UUID
    product_id: UUID | None
    product_snapshot_id: UUID | None
    initial_snapshot_id: UUID | None
    start_set_id: UUID | None
    created_at: datetime


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
    primary_character_id: UUID | None
    primary_product_character_id: UUID
    characters: tuple[ConversationCharacterCommand, ...]


@dataclass(frozen=True, slots=True)
class GenerationStateInfo:
    id: UUID
    user_id: UUID
    conversation_id: UUID
    product_id: UUID
    product_snapshot_id: UUID
    model_id: UUID
    model_name: str
    reasoning_effort: str
    request_key: str
    input_digest: str
    result_digest: str | None
    status: str
    message_count: int


@dataclass(frozen=True, slots=True)
class GetStatisticsFactsCommand:
    product_id: UUID
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class ConversationStatisticsInfo:
    generations: list[tuple]
    users: list[tuple]
    conversations: list[tuple]
    transitions: list[tuple]


@dataclass(frozen=True, slots=True, kw_only=True)
class BeginGenerationCommand:
    conversation_id: UUID
    user_id: UUID
    request_key: str
    input_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FinishGenerationCommand:
    generation_id: UUID
    user_id: UUID
    value: GenerationResult


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnedConversationCommand:
    conversation_id: UUID
    user_id: UUID
    lock: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class StartConversationCommand:
    product_id: UUID
    user_id: UUID
    start_set_id: UUID | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareRuntimeContextCommand:
    conversation_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchVersionCommand:
    conversation_id: UUID
    user_id: UUID
    target_snapshot_id: UUID
    automatic: bool = False
