from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.modules.llm.types import ExecutionInfo


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
class ConversationStarted:
    id: UUID
    product_snapshot_id: UUID
    start_set_id: UUID


@dataclass(frozen=True, slots=True)
class VersionSwitched:
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
class RuntimeContext:
    execution: ExecutionInfo
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
