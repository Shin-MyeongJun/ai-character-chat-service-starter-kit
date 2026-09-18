# source_start/end_position은 양 끝 포함 근거 구간, conversation_revision은 대화 원문 변경 세대다.
# 출처·모델의 None은 legacy 또는 아직 기록되지 않은 값이다. ready만 벡터 검색에 참여한다.
# scope_generation은 claim 당시 예약 세대다. 새 예약은 requested_generation을 올려 후속 처리를 남긴다.
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, Literal, TypeAlias, TypeVar
from uuid import UUID

from app.modules.llm import types as LLMTypes

MemoryType: TypeAlias = Literal["summary", "fact", "event"]
MemoryIndexStatus: TypeAlias = Literal["pending", "ready", "failed"]


class StaleMemoryWorkError(RuntimeError):
    """A destructive history change made an in-flight result obsolete."""


class ContextBudgetExceededError(RuntimeError):
    def __init__(self, message: str, *, summary_required: bool) -> None:
        super().__init__(message)
        self.summary_required = summary_required


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryPolicy:
    summarization_threshold_tokens: int = 4000
    summary_batch_tokens: int = 3000
    recent_raw_tokens: int = 1200
    summary_output_tokens: int = 700
    memory_token_budget: int = 1200
    retrieval_candidates: int = 20
    retrieval_limit: int = 8
    prompt_version: str = "hypha-summary-v1"


@dataclass(frozen=True, slots=True)
class SourceMessageInfo:
    id: UUID
    sender_type: str
    content: str
    position: int
    revision: int


@dataclass(frozen=True, slots=True)
class SummaryPlanInfo:
    conversation_id: UUID
    owner_id: UUID
    conversation_revision: int
    source_messages: tuple[SourceMessageInfo, ...]
    source_digest: str
    estimated_input_tokens: int
    prompt_version: str

    @property
    def source_start_position(self) -> int:
        return self.source_messages[0].position

    @property
    def source_end_position(self) -> int:
        return self.source_messages[-1].position


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanSummarizationCommand:
    conversation_id: UUID
    owner_id: UUID
    conversation_revision: int
    messages: tuple[SourceMessageInfo, ...]
    policy: MemoryPolicy


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerateSummaryCommand:
    plan: SummaryPlanInfo
    provider: LLMTypes.LLMProvider | str | None
    model: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class GeneratedSummaryInfo:
    plan: SummaryPlanInfo
    content: str
    provider: LLMTypes.LLMProvider
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveSummaryCommand:
    generated: GeneratedSummaryInfo
    importance: float = 0.5


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidateSummarySourceCommand:
    plan: SummaryPlanInfo
    current_messages: tuple[SourceMessageInfo, ...]
    current_conversation_revision: int


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbedSummaryCommand:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID
    content: str
    content_digest: str
    conversation_revision: int
    provider: LLMTypes.EmbeddingProvider | str | None
    model: str
    output_dimension: int | None = None
    truncation: bool = False


@dataclass(frozen=True, slots=True)
class EmbeddedSummaryInfo:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID
    content_digest: str
    conversation_revision: int
    vector: tuple[float, ...]
    provider: LLMTypes.EmbeddingProvider
    model: str
    dimension: int
    settings: dict
    total_tokens: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveEmbeddingCommand:
    value: EmbeddedSummaryInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateMemoryCommand:
    conversation_id: UUID
    memory_type: MemoryType
    content: str
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateMemoryCommand:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID
    content: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DeleteMemoryCommand:
    conversation_id: UUID
    memory_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class SearchMemoriesCommand:
    conversation_id: UUID
    query_text: str
    owner_id: UUID
    top_k: int = 5
    memory_types: tuple[MemoryType, ...] | None = None
    embedding_model: str = field(kw_only=True)
    embedding_provider: LLMTypes.EmbeddingProvider | str | None = field(
        default=None, kw_only=True
    )
    output_dimension: int | None = field(default=None, kw_only=True)
    token_budget: int | None = field(default=None, kw_only=True)
    result_limit: int | None = field(default=None, kw_only=True)
    conservative_token_budget: bool = field(default=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class RetrievedMemoryInfo:
    memory_id: UUID
    memory_type: MemoryType
    content: str
    similarity_score: float
    importance: float = 0.5
    recency_score: float = 0.0
    selection_score: float = 0.0
    estimated_tokens: int = 0
    source_start_position: int | None = None
    source_end_position: int | None = None
    source_digest: str | None = None
    conversation_revision: int | None = None
    summary_provider: str | None = None
    summary_model: str | None = None
    prompt_version: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MemoryInfo:
    id: UUID
    conversation_id: UUID
    memory_type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime
    index_status: MemoryIndexStatus = "pending"
    importance: float = 0.5
    source_start_position: int | None = None
    source_end_position: int | None = None
    source_digest: str | None = None
    conversation_revision: int | None = None
    summary_provider: str | None = None
    summary_model: str | None = None
    prompt_version: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None


@dataclass(frozen=True, slots=True)
class MemoryCursor:
    created_at: datetime
    id: UUID


TMemoryItem = TypeVar("TMemoryItem")


@dataclass(frozen=True, slots=True)
class MemoryPage(Generic[TMemoryItem]):
    items: list[TMemoryItem]
    next_cursor: MemoryCursor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetMemoryCommand:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMemoriesCommand:
    conversation_id: UUID
    owner_id: UUID
    cursor: MemoryCursor | None = None
    limit: int = 50
    memory_types: Sequence[MemoryType] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLatestSummaryCommand:
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetPendingIndexCommand:
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class InvalidateConversationMemoriesCommand:
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduleMemoryWorkCommand:
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimMemoryWorkCommand:
    worker_id: str
    lease_seconds: int = 300


@dataclass(frozen=True, slots=True)
class MemoryWorkInfo:
    conversation_id: UUID
    owner_id: UUID
    scope_generation: int
    attempt_count: int
    lease_owner: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CompleteMemoryWorkCommand:
    work: MemoryWorkInfo
    more_work: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class FailMemoryWorkCommand:
    work: MemoryWorkInfo
    error_kind: str
    retryable: bool
    max_attempts: int = 5
    base_retry_seconds: int = 5
    max_retry_seconds: int = 300
