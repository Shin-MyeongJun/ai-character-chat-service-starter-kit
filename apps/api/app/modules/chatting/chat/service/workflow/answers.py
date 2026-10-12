# 답변 준비 → 생성·과금 예약 commit → LLM → staging → 저장·차감 확정.
# DB와 공급자 호출은 하나의 원자적 작업이 아니다. lease 복구는 저장된 결과만 사용한다.
"""One durable nonstream answer. Never repeat an uncertain provider call."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import structlog

from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import prompt as PromptMapper
from app.modules.chatting.chat.service.command import answers as AnswersCommandService
from app.modules.chatting.chat.service.command import (
    generation as GenerationCommandService,
)
from app.modules.chatting.chat.service.query import generation as GenerationQueryService
from app.modules.chatting.chat.service.query import messages as MessagesQueryService
from app.modules.chatting.chat.service.workflow.answer_preparation import (
    prepare_answer_context,
)
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.prompt import service as PromptService
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service import credits as BillingCreditService
from app.modules.commerce.billing.service import quotes as BillingQuoteService
from app.modules.commerce.billing.service.pricing import BillingPricingConfiguration
from app.modules.llm import types as LLMTypes
from app.modules.llm.service import TextGenerationService
from app.modules.llm.service import query as LLMQueryService

logger = structlog.get_logger(__name__)
TOKEN_ESTIMATOR = "utf8-bytes-plus-32-per-message-plus-32-v1"
ANSWER_KEY_NAMESPACE = uuid5(NAMESPACE_URL, "chatkit:answers:billing:v1")


class AnswerOrchestrator:
    def __init__(
        self,
        session_factory,
        text_service: TextGenerationService,
        memory_retriever: MemoryService.MemoryRetriever,
        *,
        config: Types.AnswerConfig | None = None,
        template: PromptTypes.TemplateInfo | None = None,
        pricing: BillingPricingConfiguration | None = None,
    ):
        self.sessions = session_factory
        self.text = text_service
        self.retriever = memory_retriever
        self.config = config or Types.AnswerConfig()
        self.template = template or PromptService.load_template()
        self.pricing = pricing

    async def _get_request(self, session, command, identity):
        existing = await AnswersCommandService.get_answer_request(
            session,
            Types.GetAnswerRequestCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                request_key=command.request_key,
            ),
        )
        if existing is not None:
            if (
                existing.conversation_id != command.conversation_id
                or (existing.answer_metadata or {}).get("identity") != identity
            ):
                raise Types.MessageConflictError(
                    "Request key was used for different input or character."
                )
            if existing.history_invalidated_at is not None:
                raise Types.MessageConflictError(
                    "The original answer history has been changed."
                )
        return existing

    async def _read_preparation(self, session, command):
        current = await AnswersCommandService.get_answer_input(
            session,
            Types.GetAnswerInputCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                message_id=command.input_message_id,
                expected_revision=command.expected_revision,
            ),
        )
        owned = ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        )
        conversation = await ConversationService.get_owned_conversation(session, owned)
        participants = await ConversationService.list_conversation_characters(
            session, owned
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
        source = await MessagesQueryService.list_memory_source(
            session,
            Types.ListMemorySourceCommand(
                conversation_id=command.conversation_id, user_id=command.user_id
            ),
        )
        snapshot = _digest(
            {
                "conversation": asdict(conversation),
                "participants": [asdict(item) for item in participants],
                "runtime": asdict(runtime),
                "model": asdict(model),
                "source": asdict(source),
            }
        )
        return current, runtime, model, conversation, snapshot

    async def _resume(self, run):
        metadata = run.answer_metadata or {}
        if run.status == "pending" and (
            metadata.get("phase") == "result_ready"
            or (
                run.answer_lease_until is not None
                and run.answer_lease_until <= datetime.now(UTC)
            )
        ):
            try:
                return await self._finalize(run.id, run.user_id, recover=True)
            except Exception as exc:
                raise Types.AnswerStorageError(
                    "Answer storage is pending recovery."
                ) from exc
        return _answer_info(run)

    async def generate_answer(
        self, command: Types.GenerateAnswerCommand
    ) -> Types.AnswerInfo:
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
        # Existing requests precede configuration, preparation, prices and expiry.
        async with self.sessions() as session, use_case_transaction(session):
            existing = await self._get_request(session, command, identity)
            if existing is None:
                if self.pricing is None or self.pricing.price_book is None:
                    raise BillingTypes.BillingPricingError(
                        "Price book is not configured."
                    )
                prepared = await self._read_preparation(session, command)
        if existing is not None:
            return await self._resume(existing)
        current, runtime, model, conversation, snapshot = prepared
        config, template, pricing = self.config, self.template, self.pricing
        if pricing is None:
            raise BillingTypes.BillingPricingError("Price book is not configured.")
        maximum = min(config.max_prompt_tokens, model.context_window)
        if maximum <= config.response_tokens:
            raise ValueError("Output reserve exceeds model context window.")
        metadata = {
            "version": 2,
            "execution_token": str(uuid4()),
            "identity": identity,
            "template": {
                "id": template.template_id,
                "version": template.version,
                "digest": template.digest,
            },
            "provider": runtime.execution.provider,
            "phase": "preparing",
            "preparation_digest": snapshot,
            "max_prompt_tokens": maximum,
            "response_tokens": config.response_tokens,
            "token_estimator": TOKEN_ESTIMATOR,
        }
        started = monotonic()
        usage = LLMTypes.TokenUsageInfo()
        prompt = None
        # Memory embedding runs without a generation/credit reservation or DB locks.
        try:
            async with asyncio.timeout(config.timeout_seconds):
                base_command = PromptTypes.BuildPromptCommand(
                    template=template,
                    runtime=runtime,
                    product_character_id=command.product_character_id,
                    current_message=PromptMapper.message_info_to_prompt(current),
                )
                base = PromptService.build_prompt(base_command)
                context = await prepare_answer_context(
                    self.sessions,
                    Types.PrepareAnswerContextCommand(
                        conversation_id=command.conversation_id,
                        owner_id=command.user_id,
                        current_message=current.content,
                        current_message_id=current.id,
                        runtime=runtime,
                        rendered_base_tokens=base.estimated_tokens,
                        max_prompt_tokens=maximum,
                        response_tokens=config.response_tokens,
                        embedding_model=config.embedding_model,
                        embedding_provider=config.embedding_provider,
                        embedding_output_dimension=config.embedding_output_dimension,
                        policy=config.memory_policy,
                    ),
                    memory_retriever=self.retriever,
                )
                prompt = PromptService.build_prompt(
                    replace(
                        base_command,
                        recent_messages=tuple(
                            PromptMapper.message_info_to_prompt(item)
                            for item in context.recent_messages
                        ),
                        memories=context.memories,
                    )
                )
                if prompt.estimated_tokens + config.response_tokens > maximum:
                    raise MemoryTypes.ContextBudgetExceededError(
                        "Rendered prompt exceeds model context window.",
                        summary_required=False,
                    )
                metadata.update(
                    phase="reserved",
                    prompt_digest=hashlib.sha256(
                        prompt.request_json.encode()
                    ).hexdigest(),
                    estimated_prompt_tokens=prompt.estimated_tokens,
                )
        except Exception as exc:
            code, retryable, uncertain = _classify_error(exc, "preparing")
            metadata = _failure(
                metadata, code, usage, retryable=retryable, uncertain=uncertain
            )
            metadata["unbilled_reason"] = "preparation_failed"
            prompt = None

        # Reacquire request/conversation locks and revalidate before any reservation.
        # This transaction owns quote + generation + credit + durable binding.
        try:
            async with self.sessions() as session, use_case_transaction(session):
                existing = await self._get_request(session, command, identity)
                if existing is None:
                    checked = await self._read_preparation(session, command)
                    if checked[-1] != snapshot or (
                        self.config,
                        self.template,
                        self.pricing,
                    ) != (config, template, pricing):
                        raise Types.MessageConflictError(
                            "Answer conditions changed; retry preparation."
                        )
                    run = await GenerationCommandService.begin_generation(
                        session,
                        Types.BeginGenerationCommand(
                            conversation_id=command.conversation_id,
                            user_id=command.user_id,
                            request_key=command.request_key,
                            input_text=current.content,
                            input_message_id=current.id,
                            expected_revision=current.revision,
                            execution=runtime.execution,
                        ),
                    )
                    if prompt is not None:
                        operation = BillingTypes.BillingOperationKind.USER_GENERATION
                        billing_request = BillingTypes.BillingRequestInfo(
                            user_id=command.user_id,
                            request_key=uuid5(
                                ANSWER_KEY_NAMESPACE,
                                f"{command.user_id}:{command.request_key}",
                            ),
                            operation_kind=operation,
                            operation_fingerprint="sha256:"
                            + _digest(
                                {
                                    "version": "answer-operation-v1",
                                    "command": asdict(command),
                                    "preparation": snapshot,
                                    "prompt_digest": metadata["prompt_digest"],
                                    "token_estimator": TOKEN_ESTIMATOR,
                                    "input_tokens": prompt.estimated_tokens,
                                    "max_output_tokens": config.response_tokens,
                                }
                            ),
                            product=BillingTypes.BillingProductInfo(
                                product_id=conversation.product_id,
                                product_snapshot_id=UUID(runtime.product_snapshot_id),
                            ),
                            execution=BillingTypes.BillingExecutionInfo(
                                model_id=runtime.execution.model_id,
                                provider=runtime.execution.provider,
                                model=runtime.execution.model,
                                reasoning_effort=runtime.execution.reasoning_effort,
                            ),
                            input_tokens=prompt.estimated_tokens,
                            max_output_tokens=config.response_tokens,
                        )
                        quote = await BillingQuoteService.create_billing_quote(
                            session,
                            BillingTypes.CreateBillingQuoteCommand(
                                request=billing_request
                            ),
                            configuration=pricing,
                        )
                        reservation = await BillingCreditService.reserve_credit(
                            session,
                            BillingTypes.ReserveCreditCommand(
                                user_id=command.user_id,
                                request_key=billing_request.request_key,
                                quote_id=quote.id,
                                request=billing_request,
                            ),
                        )
                        fingerprint = billing_request.operation_fingerprint
                        metadata["billing"] = {
                            "version": 1,
                            "request_key": str(billing_request.request_key),
                            "quote_id": str(quote.id),
                            "reservation_id": str(reservation.id),
                            "reserved_credit": reservation.reserved_credit,
                            "operation_fingerprint": fingerprint,
                        }
                    lease = datetime.now(UTC) + timedelta(
                        seconds=config.timeout_seconds + 60
                    )
                    await AnswersCommandService.update_answer(
                        session,
                        Types.UpdateAnswerCommand(
                            generation_id=run.id,
                            user_id=command.user_id,
                            metadata=metadata,
                            lease_until=lease,
                        ),
                    )
        except (ValueError, LookupError, Types.MessageConflictError):
            raise
        except Exception as exc:
            # Reservation commit may have succeeded despite a lost acknowledgement.
            # A persisted request is never permission to execute this call again.
            try:
                async with self.sessions() as session, use_case_transaction(session):
                    existing = await self._get_request(session, command, identity)
            except Exception:
                existing = None
            if existing is not None:
                return await self._resume(existing)
            raise Types.AnswerStorageError(
                "Reservation storage is uncertain; replay the same request key."
            ) from exc

        if existing is not None:
            return await self._resume(existing)
        if prompt is None:
            return await self._complete_staged(run.id, command.user_id)

        # Commit has returned. Persist calling before starting the external request.
        # A stage/commit error is uncertain storage, never a reason to release funds.
        metadata = {**metadata, "phase": "calling"}
        try:
            await self._stage(run.id, command.user_id, metadata, lease)
        except Exception as exc:
            return await self._reconcile_storage(run.id, command.user_id, exc)
        try:
            async with asyncio.timeout(config.timeout_seconds):
                result = await self.text.generate_text(
                    LLMTypes.GenerateTextCommand(
                        prompt.request_json,
                        model=run.model_name,
                        provider=runtime.execution.provider,
                        reasoning_effort=None
                        if run.reasoning_effort == "none"
                        else run.reasoning_effort,
                        max_output_tokens=config.response_tokens,
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
                metadata, "cancelled", usage, uncertain=True, outcome="cancelled"
            )
            try:
                await self._stage(run.id, command.user_id, metadata, lease)
                await self._finalize(run.id, command.user_id)
            except Exception:
                logger.warning(
                    "answer_cancel_recovery_required", generation_id=str(run.id)
                )
            raise
        except Exception as exc:
            code, retryable, uncertain = _classify_error(exc, metadata["phase"])
            if isinstance(exc, LLMTypes.LLMError) and exc.usage is not None:
                usage = exc.usage
            metadata = _failure(
                metadata, code, usage, retryable=retryable, uncertain=uncertain
            )
        metadata["latency_ms"] = min(int((monotonic() - started) * 1000), 2**31 - 1)
        try:
            # New session verifies durable state + execution token + lease before
            # recording even a timeout/cancellation as a terminal failure candidate.
            await self._stage(run.id, command.user_id, metadata, lease)
        except Exception as exc:
            return await self._reconcile_storage(run.id, command.user_id, exc)
        return await self._complete_staged(run.id, command.user_id)

    async def _reconcile_storage(self, generation_id, user_id, error):
        try:
            async with self.sessions() as session:
                run = await GenerationQueryService.get_generation_state(
                    session,
                    Types.GetGenerationStateCommand(
                        generation_id=generation_id, user_id=user_id
                    ),
                )
            if run.status != "pending":
                return _answer_info(run)
            if (run.answer_metadata or {}).get("phase") == "result_ready":
                return await self._complete_staged(generation_id, user_id)
        except Exception as exc:
            error = exc
        raise Types.AnswerStorageError(
            "Answer storage is pending recovery; replay the same request key."
        ) from error

    async def _complete_staged(self, generation_id, user_id):
        try:
            return await self._finalize(generation_id, user_id)
        except Exception as exc:
            # A commit acknowledgement can be lost after the whole operation won.
            # Only a fresh durable terminal state proves completion; otherwise leave
            # the staging and reservation untouched for replay/supervisor recovery.
            try:
                async with self.sessions() as session:
                    run = await GenerationQueryService.get_generation_state(
                        session,
                        Types.GetGenerationStateCommand(
                            generation_id=generation_id, user_id=user_id
                        ),
                    )
                if run.status != "pending":
                    return _answer_info(run)
            except Exception:
                pass
            raise Types.AnswerStorageError(
                "Answer storage is pending recovery; replay the same request key."
            ) from exc

    async def _stage(self, generation_id, user_id, metadata, lease):
        async with self.sessions() as session:
            await AnswersCommandService.update_answer(
                session,
                Types.UpdateAnswerCommand(
                    generation_id=generation_id,
                    user_id=user_id,
                    metadata=metadata,
                    lease_until=lease,
                    execution_token=metadata.get("execution_token"),
                ),
            )

    # 잠금 아래 생성 상태를 다시 확인하고 staging된 결과를 메시지·usage·memory 예약에
    # 반영한다.
    # recover=True라도 공급자를 다시 호출하지 않는다.
    async def _finalize(self, generation_id, user_id, *, recover=False):
        async with self.sessions() as session, use_case_transaction(session):
            run = await GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            await ConversationService.get_owned_conversation(
                session,
                ConversationTypes.OwnedConversationCommand(
                    conversation_id=run.conversation_id, user_id=user_id, lock=True
                ),
            )
            run = await GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            if run.status != "pending":
                return _answer_info(run)
            metadata = run.answer_metadata or {}
            if (
                recover
                and metadata.get("phase") != "result_ready"
                and (
                    run.answer_lease_until is None
                    or run.answer_lease_until > datetime.now(UTC)
                )
            ):
                return _answer_info(run)
            # 복구 시 결과가 없으면 호출을 재실행하지 않고 preparing/calling에 따라
            # 실패와 불확실성을 기록한다.
            if metadata.get("phase") != "result_ready":
                if not recover:
                    raise Types.AnswerStorageError("No durable provider result.")
                metadata = _failure(
                    metadata,
                    "interrupted_uncertain"
                    if metadata.get("phase") == "calling"
                    else "interrupted_before_call",
                    LLMTypes.TokenUsageInfo(),
                    uncertain=metadata.get("phase") == "calling",
                )
                await AnswersCommandService.update_answer(
                    session,
                    Types.UpdateAnswerCommand(
                        generation_id=generation_id,
                        user_id=user_id,
                        metadata=metadata,
                        lease_until=datetime.now(UTC),
                        execution_token=metadata.get("execution_token"),
                        recover=True,
                    ),
                )
            usage = metadata.get("usage", {})
            billing = metadata.get("billing")
            if (
                metadata.get("version") == 2
                and billing is None
                and (
                    metadata.get("unbilled_reason") != "preparation_failed"
                    or metadata.get("outcome") == "succeeded"
                )
            ):
                raise Types.AnswerStorageError("Missing answer billing binding.")
            value = Types.GenerationResult(
                input_tokens=_usage_count(usage.get("input_tokens")),
                output_tokens=_usage_count(usage.get("output_tokens")),
                cost_credit=billing["reserved_credit"] if billing else 0,
                messages=(
                    Types.GeneratedMessage(
                        UUID(metadata["identity"]["product_character_id"]),
                        metadata["content"],
                    ),
                )
                if metadata["outcome"] == "succeeded"
                else (),
                outcome=metadata["outcome"],
                latency_ms=metadata.get("latency_ms"),
            )
            finished = await finish_generation_and_schedule_memory(
                session,
                Types.FinishGenerationCommand(
                    generation_id=generation_id, user_id=user_id, value=value
                ),
            )
            if billing is not None:
                if finished.status == "succeeded":
                    settled = await BillingCreditService.commit_credit_reservation(
                        session,
                        BillingTypes.CommitCreditReservationCommand(
                            user_id=user_id,
                            request_key=UUID(billing["request_key"]),
                            reservation_id=UUID(billing["reservation_id"]),
                            result_id=generation_id,
                        ),
                    )
                else:
                    settled = await BillingCreditService.release_credit_reservation(
                        session,
                        BillingTypes.ReleaseCreditReservationCommand(
                            user_id=user_id,
                            request_key=UUID(billing["request_key"]),
                            reservation_id=UUID(billing["reservation_id"]),
                        ),
                    )
                if settled.reserved_credit != billing["reserved_credit"]:
                    raise Types.AnswerStorageError(
                        "Answer charge differs from reservation."
                    )
            if metadata.get("error_code") == "summary_required":
                await MemoryService.schedule_memory_work(
                    session,
                    MemoryTypes.ScheduleMemoryWorkCommand(
                        conversation_id=run.conversation_id, owner_id=user_id
                    ),
                )
            run = await GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=generation_id, user_id=user_id
                ),
            )
            return _answer_info(run)

    # 반환값은 조회한 만료 생성 수다. 개별 복구 실패도 포함하므로 성공 건수로 해석하지
    # 않는다.
    # lease가 만료된 답변만 순회한다. 결과가 없으면 중단 단계를 구분해 실패 처리하고
    # 저장된 결과는 완료를 재시도한다.
    async def recover_answers(self) -> int:
        async with self.sessions() as session:
            expired = await AnswersCommandService.list_expired_answers(
                session, Types.ListExpiredAnswersCommand(now=datetime.now(UTC))
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


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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
    billing = metadata.get("billing")
    price_credit = billing.get("reserved_credit") if isinstance(billing, dict) else None
    return Types.AnswerInfo(
        run.id,
        run.status,
        metadata.get("content") if run.status == "succeeded" else None,
        run.model_name,
        "stale" if run.status == "stale" else metadata.get("error_code"),
        metadata.get("retryable", False),
        metadata.get("uncertain", False),
        price_credit if isinstance(price_credit, int) and price_credit >= 0 else None,
    )


# 성공 생성 저장과 기억 작업 예약을 같은 트랜잭션으로 묶는다. 완료 재전송은 세대를 다시 올리지 않는다.
async def finish_generation_and_schedule_memory(
    session, command: Types.FinishGenerationCommand
) -> Types.GenerationInfo:
    """The successful response and queue generation commit atomically."""
    async with use_case_transaction(session):
        before = await GenerationQueryService.get_generation_state(
            session,
            Types.GetGenerationStateCommand(
                generation_id=command.generation_id, user_id=command.user_id
            ),
        )
        await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=before.conversation_id,
                user_id=command.user_id,
                lock=True,
            ),
        )
        before = await GenerationQueryService.get_generation_state(
            session,
            Types.GetGenerationStateCommand(
                generation_id=command.generation_id, user_id=command.user_id
            ),
        )
        result = await GenerationCommandService.finish_generation(session, command)
        if result.status == "succeeded" and before.status == "pending":
            generation = await GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=command.generation_id, user_id=command.user_id
                ),
            )
            await MemoryService.schedule_memory_work(
                session,
                MemoryTypes.ScheduleMemoryWorkCommand(
                    conversation_id=generation.conversation_id,
                    owner_id=command.user_id,
                ),
            )
        return result
