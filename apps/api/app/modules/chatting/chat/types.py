# position은 DB 전역 순번(연속 번호 아님), revision은 개별 메시지 수정 버전이다.
# product_character_id는 상품 구성 슬롯, character_id는 원본, product_snapshot_id는
# 사용 버전이다.
# GenerationInfo.message_count는 원래 성공 출력 수이며 이력 삭제 후에도 유지된다.
# answer_lease_until=None인 legacy 생성은 답변 lease 복구 대상에서 제외된다.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.llm import types as LLMTypes
from app.modules.llm.types import ExecutionView


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
    """Trusted character text; AI output is saved by finish_generation."""

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
class ListConversationPreviewsCommand:
    user_id: UUID
    conversation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMemorySourceCommand:
    conversation_id: UUID
    user_id: UUID
    after_position: int = 0
    through_position: int | None = None
    limit: int = 10000


@dataclass(frozen=True, slots=True)
class MemorySourceInfo:
    messages: tuple[MessageInfo, ...]
    truncated: bool


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
    answer_metadata: dict | None = None
    answer_lease_until: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class BeginGenerationCommand:
    conversation_id: UUID
    user_id: UUID
    request_key: str
    input_text: str
    input_message_id: UUID | None = None
    expected_revision: int | None = None
    execution: ExecutionView | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinishGenerationCommand:
    generation_id: UUID
    user_id: UUID
    value: GenerationResult


@dataclass(frozen=True, slots=True, kw_only=True)
class GetGenerationStateCommand:
    generation_id: UUID
    user_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAnswerRequestCommand:
    conversation_id: UUID
    user_id: UUID
    request_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetAnswerInputCommand:
    conversation_id: UUID
    user_id: UUID
    message_id: UUID
    expected_revision: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateAnswerCommand:
    generation_id: UUID
    user_id: UUID
    metadata: dict
    lease_until: datetime
    execution_token: str | None = None
    recover: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ListExpiredAnswersCommand:
    now: datetime
    limit: int = 100


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerateAnswerCommand:
    conversation_id: UUID
    user_id: UUID
    request_key: str
    input_message_id: UUID
    expected_revision: int
    product_character_id: UUID


@dataclass(frozen=True, slots=True)
class AnswerInfo:
    generation_id: UUID
    status: str
    content: str | None
    model: str
    error_code: str | None
    retryable: bool
    uncertain: bool
    price_credit: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AnswerConfig:
    max_prompt_tokens: int = 8000
    response_tokens: int = 1200
    timeout_seconds: float = 90
    embedding_model: str = "voyage-large-2"
    embedding_provider: str = "voyage"
    embedding_output_dimension: int | None = None
    memory_policy: MemoryTypes.MemoryPolicy = field(
        default_factory=MemoryTypes.MemoryPolicy
    )

    def __post_init__(self):
        if (
            not 1 <= self.response_tokens < self.max_prompt_tokens
            or not 0 < self.timeout_seconds <= 600
        ):
            raise ValueError(
                "Invalid answer token limits or timeout (maximum 600 seconds)."
            )


class AnswerStorageError(RuntimeError):
    """The durable lease/recovery path must reconcile this run; do not call again."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareAnswerContextCommand:
    conversation_id: UUID
    owner_id: UUID
    current_message: str
    max_prompt_tokens: int
    response_tokens: int
    embedding_model: str
    embedding_provider: LLMTypes.EmbeddingProvider | str | None = None
    embedding_output_dimension: int | None = None
    policy: MemoryTypes.MemoryPolicy = field(default_factory=MemoryTypes.MemoryPolicy)
    current_message_id: UUID | None = None
    runtime: ConversationTypes.ConversationRuntimeView | None = None
    rendered_base_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class PromptBudgetInfo:
    maximum: int
    base: int
    memories: int
    recent_messages: int
    current_message: int
    response_reserve: int


@dataclass(frozen=True, slots=True)
class AnswerContextInfo:
    runtime: ConversationTypes.ConversationRuntimeView
    memories: tuple[MemoryTypes.RetrievedMemoryInfo, ...]
    recent_messages: tuple[MessageInfo, ...]
    current_message: str
    budget: PromptBudgetInfo
    memory_state: str


@dataclass(frozen=True, slots=True)
class ProcessMemoryWorkCommand:
    work: MemoryTypes.MemoryWorkInfo
    policy: MemoryTypes.MemoryPolicy
    models: MemoryTypes.MemoryModelConfig


@dataclass(frozen=True, slots=True)
class GetAccountGenerationStatisticsCommand:
    user_id: UUID
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class AccountGenerationStatisticsInfo:
    pending: int
    succeeded: int
    failed: int
    cancelled: int
    stale: int
