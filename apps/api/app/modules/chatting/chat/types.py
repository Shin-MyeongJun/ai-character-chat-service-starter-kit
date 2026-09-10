from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


class MessageConflictError(Exception):
    """The requested history mutation conflicts with the current state."""


class MessagePermissionError(Exception):
    """A public user command cannot write a character message."""


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateMessageCommand:
    conversation_id: UUID
    user_id: UUID
    request_key: str
    content: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateCharacterMessageCommand(CreateMessageCommand):
    """Trusted internal character text; actual AI output is saved by finish_generation."""

    product_character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplaceMessageCommand:
    conversation_id: UUID
    user_id: UUID
    message_id: UUID
    expected_revision: int
    content: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplaceCharacterMessageCommand(ReplaceMessageCommand):
    """Internal correction of character output, not a new generation fact."""

    product_character_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RewindMessagesCommand:
    conversation_id: UUID
    user_id: UUID
    message_id: UUID


@dataclass(frozen=True, slots=True)
class MessageCursor:
    conversation_id: UUID
    position: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMessagesCommand:
    conversation_id: UUID
    user_id: UUID
    cursor: MessageCursor | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class MessageInfo:
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


@dataclass(frozen=True, slots=True)
class MessagePageInfo:
    items: tuple[MessageInfo, ...]
    next_cursor: MessageCursor | None


@dataclass(frozen=True, slots=True)
class RewindMessagesInfo:
    deleted_count: int


@dataclass(frozen=True, slots=True)
class MessageRequestInfo:
    input_digest: str
    message_id: UUID | None


@dataclass(frozen=True, slots=True)
class GetStatisticsFactsCommand:
    product_id: UUID
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class GenerationStatisticsInfo:
    generations: list[tuple]
    users: list[tuple]


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
    history_invalidated_at: datetime | None


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
