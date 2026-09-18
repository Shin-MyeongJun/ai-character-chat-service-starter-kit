# 모델 DB 식별자(model_id)와 공급자에게 보내는 모델명(model)을 구분한다.
# usage의 None은 공급자가 값을 제공하지 않았다는 뜻이며 0 사용량과 다르다.
# retryable은 오류 분류 정보다. 이 값 자체가 재시도나 중복 과금 방지를 실행하지 않는다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID


class LLMProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


class EmbeddingProvider(StrEnum):
    OPENAI = "openai"
    VOYAGE = "voyage"


class EmbeddingPurpose(StrEnum):
    QUERY = "query"
    DOCUMENT = "document"


class ReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


class LLMErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    CONNECTION = "connection"
    PROVIDER = "provider"


class EmbeddingErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    CONNECTION = "connection"
    INVALID_RESPONSE = "invalid_response"
    PROVIDER = "provider"


@dataclass(frozen=True, slots=True)
class TokenUsageInfo:
    """Provider-reported usage normalized without serializing the SDK response."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_creation_5m_input_tokens: int | None = None
    cache_creation_1h_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingUsageInfo:
    """Usage reported by the embedding provider."""

    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingResultInfo:
    embeddings: tuple[tuple[float, ...], ...]
    dimension: int
    provider: EmbeddingProvider
    model: str
    usage: EmbeddingUsageInfo


@dataclass(frozen=True, slots=True)
class LLMResultInfo:
    content: str
    provider: LLMProvider
    model: str
    usage: TokenUsageInfo
    response_id: str | None = None
    request_id: str | None = None
    status: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelOptionInfo:
    provider: LLMProvider
    model: str
    reasoning_efforts: frozenset[ReasoningEffort]


class LLMError(RuntimeError):
    """Stable provider-error contract for callers such as credit and chat services."""

    def __init__(
        self,
        message: str,
        *,
        kind: LLMErrorKind,
        provider: LLMProvider,
        model: str,
        retryable: bool,
        request_id: str | None = None,
        status_code: int | None = None,
        usage: TokenUsageInfo | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.request_id = request_id
        self.status_code = status_code
        self.usage = usage


class EmbeddingError(RuntimeError):
    """Stable provider-error contract for embedding callers."""

    def __init__(
        self,
        message: str,
        *,
        kind: EmbeddingErrorKind,
        provider: EmbeddingProvider,
        model: str,
        retryable: bool,
        request_id: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.request_id = request_id
        self.status_code = status_code


class UnsupportedModelError(ValueError):
    pass


class UnsupportedReasoningEffortError(ValueError):
    pass


class UnsupportedEmbeddingModelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelNoticeView:
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


@dataclass(frozen=True, slots=True)
class ExecutionView:
    model_id: UUID
    provider: str
    model: str
    reasoning_effort: str
    replacement: bool
    scheduled_at: datetime | None
    replacement_unavailable: bool = False
    planned_model_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: UUID
    provider_id: UUID
    model_name: str
    is_enabled: bool
    capabilities: dict
    retirement_announced_at: datetime | None
    shutdown_at: datetime | None
    context_window: int = 8000


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    id: UUID
    name: str
    is_enabled: bool


@dataclass(frozen=True, slots=True)
class GetModelCommand:
    model_id: UUID


@dataclass(frozen=True, slots=True)
class GetProviderCommand:
    provider_id: UUID


@dataclass(frozen=True, slots=True)
class ValidateModelCommand:
    model_id: UUID
    reasoning_effort: str


if TYPE_CHECKING:
    from app.modules.content.product.types import ProductSnapshotInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class AnnounceRetirementCommand:
    actor_id: UUID
    model_id: UUID
    announced_at: datetime
    shutdown_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionNoticeCommand:
    snapshot: ProductSnapshotInfo
    now: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolveExecutionCommand:
    snapshot_id: UUID
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class GenerateTextCommand:
    request_json: str
    model: str
    reasoning_effort: ReasoningEffort | str | None = None
    max_output_tokens: int | None = None
    provider: LLMProvider | str | None = None


@dataclass(frozen=True, slots=True)
class EmbedTextsCommand:
    texts: tuple[str, ...]
    model: str
    purpose: EmbeddingPurpose | str
    provider: EmbeddingProvider | str | None = None
    truncation: bool = False
    output_dimension: int | None = None
