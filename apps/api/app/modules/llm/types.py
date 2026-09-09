from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class LLMProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


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


@dataclass(frozen=True, slots=True)
class TokenUsage:
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
class LLMResult:
    content: str
    provider: LLMProvider
    model: str
    usage: TokenUsage
    response_id: str | None = None
    request_id: str | None = None
    status: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelOption:
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
        usage: TokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.provider = provider
        self.model = model
        self.retryable = retryable
        self.request_id = request_id
        self.status_code = status_code
        self.usage = usage


class UnsupportedModelError(ValueError):
    pass


class UnsupportedReasoningEffortError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelNotice:
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
class ExecutionInfo:
    model_id: UUID
    provider: str
    model: str
    reasoning_effort: str
    replacement: bool
    scheduled_at: datetime | None
    replacement_unavailable: bool = False
    planned_model_id: UUID | None = None
