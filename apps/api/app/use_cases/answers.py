# 답변 흐름: 요청 예약 → 세션 종료 → 문맥 검색·LLM → 결과 staging → 메시지·사용량·기억 예약 확정.
# DB와 공급자 호출은 하나의 원자적 작업이 아니다. lease 복구는 저장된 결과만 사용한다.
"""One durable nonstream answer. Never repeat an uncertain provider call."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

import structlog
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.prompt import service as PromptService
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.llm import types as LLMTypes
from app.modules.llm.service import TextGenerationService
from app.modules.llm.service import query as LLMQueryService
from app.use_cases.answer_preparation import (
    PrepareAnswerContextCommand,
    prepare_answer_context,
)
from app.use_cases.memory import finish_generation_and_schedule_memory

logger = structlog.get_logger(__name__)


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


class AnswerOrchestrator:
    def __init__(
        self,
        session_factory,
        text_service: TextGenerationService,
        memory_retriever: MemoryService.MemoryRetriever,
        *,
        config: AnswerConfig | None = None,
        template: PromptTypes.TemplateInfo | None = None,
    ):
        self.sessions = session_factory
        self.text = text_service
        self.retriever = memory_retriever
        self.config = config or AnswerConfig()
        self.template = template or PromptService.load_template()

    # 저장된 마지막 사용자 메시지와 지정 캐릭터로 답변 하나를 만든다. 같은 키의 완료/진행 결과는 재사용한다.
    # 예약 이후 외부 호출과 결과 staging은 별도 단계이며, 저장 실패는 lease 복구로 이어질 수 있다.
    async def generate_answer(self, command: GenerateAnswerCommand) -> AnswerInfo:
        if (
            not command.request_key.strip()
            or len(command.request_key) > 128
            or command.expected_revision < 1
        ):
            raise ValueError("Invalid answer request key or revision.")
        identity = {
            "input_message_id": str(command.input_message_id),
            "expected_revision": command.expected_revision,
            "product_character_id": str(command.product_character_id),
        }
        async with self.sessions() as session, use_case_transaction(session):
            existing = await ChatService.get_answer_request(
                session,
                ChatTypes.GetAnswerRequestCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    request_key=command.request_key,
                ),
            )
            # 같은 키는 공급자를 다시 호출하지 않는다. 다른 입력·캐릭터 또는 변경된 이력은 충돌이다.
            if existing is not None:
                if (
                    existing.conversation_id != command.conversation_id
                    or (existing.answer_metadata or {}).get("identity") != identity
                ):
                    raise ChatTypes.MessageConflictError(
                        "Request key was used for different input or character."
                    )
                if existing.history_invalidated_at is not None:
                    raise ChatTypes.MessageConflictError(
                        "The original answer history has been changed."
                    )
                return _answer_info(existing)
            current = await ChatService.get_answer_input(
                session,
                ChatTypes.GetAnswerInputCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    message_id=command.input_message_id,
                    expected_revision=command.expected_revision,
                ),
            )
            participants = await ConversationService.list_conversation_characters(
                session,
                ConversationTypes.OwnedConversationCommand(
                    conversation_id=command.conversation_id, user_id=command.user_id
                ),
            )
            if command.product_character_id not in {
                c.product_character_id for c in participants
            }:
                raise ValueError("Select exactly one participating answer character.")
            runtime = await ConversationService.prepare_runtime_context(
                session,
                ConversationTypes.PrepareRuntimeContextCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    activation_text=current.content,
                ),
            )
            model = await LLMQueryService.get_model(
                session, LLMTypes.GetModelCommand(runtime.execution.model_id)
            )
            if model is None:
                raise LLMTypes.UnsupportedModelError("Execution model is unavailable.")
            maximum = min(self.config.max_prompt_tokens, model.context_window)
            if maximum <= self.config.response_tokens:
                raise ValueError("Output reserve exceeds model context window.")
            run = await ChatService.begin_generation(
                session,
                ChatTypes.BeginGenerationCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    request_key=command.request_key,
                    input_text=current.content,
                    input_message_id=current.id,
                    expected_revision=current.revision,
                    execution=runtime.execution,
                ),
            )
            lease = datetime.now(UTC) + timedelta(
                seconds=self.config.timeout_seconds + 60
            )
            metadata = {
                "identity": identity,
                "template": {
                    "id": self.template.template_id,
                    "version": self.template.version,
                    "digest": self.template.digest,
                },
                "provider": runtime.execution.provider,
                "phase": "preparing",
                "max_prompt_tokens": maximum,
                "response_tokens": self.config.response_tokens,
            }
            await ChatService.update_answer(
                session,
                ChatTypes.UpdateAnswerCommand(
                    generation_id=run.id,
                    user_id=command.user_id,
                    metadata=metadata,
                    lease_until=lease,
                ),
            )
        started = monotonic()
        usage = LLMTypes.TokenUsageInfo()
        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                base_command = PromptTypes.BuildPromptCommand(
                    template=self.template,
                    runtime=runtime,
                    product_character_id=command.product_character_id,
                    current_message=current,
                )
                base = PromptService.build_prompt(base_command)
                context = await prepare_answer_context(
                    self.sessions,
                    PrepareAnswerContextCommand(
                        conversation_id=command.conversation_id,
                        owner_id=command.user_id,
                        current_message=current.content,
                        current_message_id=current.id,
                        runtime=runtime,
                        rendered_base_tokens=base.estimated_tokens,
                        max_prompt_tokens=maximum,
                        response_tokens=self.config.response_tokens,
                        embedding_model=self.config.embedding_model,
                        embedding_provider=self.config.embedding_provider,
                        embedding_output_dimension=self.config.embedding_output_dimension,
                        policy=self.config.memory_policy,
                    ),
                    memory_retriever=self.retriever,
                )
                prompt = PromptService.build_prompt(
                    replace(
                        base_command,
                        recent_messages=context.recent_messages,
                        memories=context.memories,
                    )
                )
                if prompt.estimated_tokens + self.config.response_tokens > maximum:
                    raise MemoryTypes.ContextBudgetExceededError(
                        "Rendered prompt exceeds model context window.",
                        summary_required=False,
                    )
                metadata = {
                    **metadata,
                    "phase": "calling",
                    "prompt_digest": hashlib.sha256(
                        prompt.request_json.encode()
                    ).hexdigest(),
                    "estimated_prompt_tokens": prompt.estimated_tokens,
                }
                # calling 단계를 먼저 저장한다. 이후 프로세스가 중단되면 호출 성공 여부를 알 수 없다고 복구한다.
                await self._stage(run.id, command.user_id, metadata, lease)
                result = await self.text.generate_text(
                    LLMTypes.GenerateTextCommand(
                        prompt.request_json,
                        model=run.model_name,
                        provider=runtime.execution.provider,
                        reasoning_effort=None
                        if run.reasoning_effort == "none"
                        else run.reasoning_effort,
                        max_output_tokens=self.config.response_tokens,
                    )
                )
                if not isinstance(result, LLMTypes.LLMResultInfo):
                    raise TypeError("invalid_result")
                if not isinstance(result.usage, LLMTypes.TokenUsageInfo):
                    raise TypeError("invalid_usage")
                usage = result.usage
                if (
                    result.provider != runtime.execution.provider
                    or not isinstance(result.model, str)
                    or not result.model.strip()
                ):
                    raise ValueError("invalid_result")
                _validate_result(result)
                metadata = {
                    **metadata,
                    "phase": "result_ready",
                    "content": result.content,
                    "usage": asdict(usage),
                    "response_id": result.response_id,
                    "outcome": "succeeded",
                }
        except asyncio.CancelledError:
            metadata = _failure(
                metadata,
                "cancelled",
                usage,
                uncertain=metadata["phase"] == "calling",
                outcome="cancelled",
            )
            try:
                await self._stage(run.id, command.user_id, metadata, lease)
                await self._finalize(run.id, command.user_id)
            except Exception:  # noqa: BLE001 - cancellation cleanup is recovered by lease
                logger.warning(
                    "answer_cancel_recovery_required", generation_id=str(run.id)
                )
            raise
        except Exception as exc:  # noqa: BLE001 - persist normalized failure at task boundary
            code, retryable, uncertain = _classify_error(exc, metadata["phase"])
            if isinstance(exc, LLMTypes.LLMError) and exc.usage is not None:
                usage = exc.usage
            metadata = _failure(
                metadata, code, usage, retryable=retryable, uncertain=uncertain
            )
        metadata["latency_ms"] = min(int((monotonic() - started) * 1000), 2**31 - 1)
        try:
            await self._stage(run.id, command.user_id, metadata, lease)
            return await self._finalize(run.id, command.user_id)
        except Exception as exc:
            logger.warning(
                "answer_storage_recovery_required",
                generation_id=str(run.id),
                error_kind=type(exc).__name__,
            )
            raise AnswerStorageError(
                "Answer storage is pending recovery; replay the same request key."
            ) from exc

    async def _stage(self, generation_id, user_id, metadata, lease):
        async with self.sessions() as session:
            await ChatService.update_answer(
                session,
                ChatTypes.UpdateAnswerCommand(
                    generation_id=generation_id,
                    user_id=user_id,
                    metadata=metadata,
                    lease_until=lease,
                ),
            )

    # 잠금 아래 생성 상태를 다시 확인하고 staging된 결과를 메시지·usage·memory 예약에 반영한다.
    # recover=True라도 공급자를 다시 호출하지 않는다.
    async def _finalize(self, generation_id, user_id, *, recover=False):
        async with self.sessions() as session, use_case_transaction(session):
            run = await ChatService.get_generation_state(
                session,
                ChatTypes.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            await ConversationService.get_owned_conversation(
                session,
                ConversationTypes.OwnedConversationCommand(
                    conversation_id=run.conversation_id, user_id=user_id, lock=True
                ),
            )
            run = await ChatService.get_generation_state(
                session,
                ChatTypes.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            if run.status != "pending":
                return _answer_info(run)
            metadata = run.answer_metadata or {}
            if recover and (
                run.answer_lease_until is None
                or run.answer_lease_until > datetime.now(UTC)
            ):
                return _answer_info(run)
            # 복구 시 결과가 없으면 호출을 재실행하지 않고 preparing/calling에 따라 실패와 불확실성을 기록한다.
            if metadata.get("phase") != "result_ready":
                if not recover:
                    raise AnswerStorageError("No durable provider result.")
                metadata = _failure(
                    metadata,
                    "interrupted_uncertain"
                    if metadata.get("phase") == "calling"
                    else "interrupted_before_call",
                    LLMTypes.TokenUsageInfo(),
                    uncertain=metadata.get("phase") == "calling",
                )
                await ChatService.update_answer(
                    session,
                    ChatTypes.UpdateAnswerCommand(
                        generation_id=generation_id,
                        user_id=user_id,
                        metadata=metadata,
                        lease_until=datetime.now(UTC),
                    ),
                )
            usage = metadata.get("usage", {})
            value = ChatTypes.GenerationResult(
                input_tokens=_usage_count(usage.get("input_tokens")),
                output_tokens=_usage_count(usage.get("output_tokens")),
                cost_credit=0,
                messages=(
                    ChatTypes.GeneratedMessage(
                        UUID(metadata["identity"]["product_character_id"]),
                        metadata["content"],
                    ),
                )
                if metadata["outcome"] == "succeeded"
                else (),
                outcome=metadata["outcome"],
                latency_ms=metadata.get("latency_ms"),
            )
            await finish_generation_and_schedule_memory(
                session,
                ChatTypes.FinishGenerationCommand(
                    generation_id=generation_id, user_id=user_id, value=value
                ),
            )
            if metadata.get("error_code") == "summary_required":
                await MemoryService.schedule_memory_work(
                    session,
                    MemoryTypes.ScheduleMemoryWorkCommand(
                        conversation_id=run.conversation_id, owner_id=user_id
                    ),
                )
            run = await ChatService.get_generation_state(
                session,
                ChatTypes.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            return _answer_info(run)

    # 반환값은 조회한 만료 생성 수다. 개별 복구 실패도 포함하므로 성공 건수로 해석하지 않는다.
    # lease가 만료된 답변만 순회한다. 결과가 없으면 중단 단계를 구분해 실패 처리하고 저장된 결과는 완료를 재시도한다.
    async def recover_answers(self) -> int:
        async with self.sessions() as session:
            expired = await ChatService.list_expired_answers(
                session, ChatTypes.ListExpiredAnswersCommand(now=datetime.now(UTC))
            )
        for run in expired:
            try:
                await self._finalize(run.id, run.user_id, recover=True)
            except Exception as exc:  # noqa: BLE001 - isolate recovery of each conversation
                logger.warning(
                    "answer_recovery_failed",
                    generation_id=str(run.id),
                    error_kind=type(exc).__name__,
                )
        return len(expired)


def _usage_count(value):
    return value if type(value) is int and 0 <= value < 2**31 else 0


def _validate_result(result):
    if not isinstance(result.content, str) or not result.content.strip():
        raise ValueError("empty_response")
    if (
        len(result.content) > 200000
        or result.status not in (None, "completed")
        or result.finish_reason
        not in (None, "completed", "end_turn", "stop_sequence", "mock")
    ):
        raise ValueError("invalid_result")
    for value in (result.usage.input_tokens, result.usage.output_tokens):
        if type(value) is not int or not 0 <= value < 2**31:
            raise ValueError("invalid_usage")


def _classify_error(exc, phase):
    if isinstance(exc, MemoryTypes.ContextBudgetExceededError):
        return (
            "summary_required" if exc.summary_required else "fixed_context_exceeded",
            exc.summary_required,
            False,
        )
    if isinstance(
        exc, (LLMTypes.UnsupportedModelError, LLMTypes.UnsupportedReasoningEffortError)
    ):
        return "unsupported_model", False, False
    if isinstance(exc, LLMTypes.LLMError):
        uncertain = exc.kind in (
            LLMTypes.LLMErrorKind.TIMEOUT,
            LLMTypes.LLMErrorKind.CONNECTION,
            LLMTypes.LLMErrorKind.PROVIDER,
        )
        return "llm_" + exc.kind.value, exc.retryable and not uncertain, uncertain
    if isinstance(exc, LLMTypes.UnsupportedEmbeddingModelError):
        return "memory_model_unavailable", False, False
    if isinstance(exc, LLMTypes.EmbeddingError):
        return "memory_" + exc.kind.value, exc.retryable, False
    if isinstance(exc, TimeoutError):
        return "timeout", phase != "calling", phase == "calling"
    if isinstance(exc, (ValueError, TypeError)) and str(exc) in (
        "empty_response",
        "invalid_result",
        "invalid_usage",
    ):
        return str(exc), False, False
    return "internal_error", False, phase == "calling"


def _failure(
    metadata, code, usage, *, retryable=False, uncertain=False, outcome="failed"
):
    return {
        **metadata,
        "phase": "result_ready",
        "outcome": outcome,
        "error_code": code,
        "retryable": retryable,
        "uncertain": uncertain,
        "usage": asdict(usage),
        "usage_known": usage.input_tokens is not None
        and usage.output_tokens is not None,
    }


def _answer_info(run):
    metadata = run.answer_metadata or {}
    return AnswerInfo(
        run.id,
        run.status,
        metadata.get("content") if run.status == "succeeded" else None,
        run.model_name,
        "stale" if run.status == "stale" else metadata.get("error_code"),
        metadata.get("retryable", False),
        metadata.get("uncertain", False),
    )
