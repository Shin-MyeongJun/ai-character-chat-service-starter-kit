# 워커의 기억 작업: 읽기 → 외부 요약/임베딩 → 잠금 후 원문 재검증을 수행한다.
# 외부 호출 성공 뒤 DB 저장이 실패할 수 있으며 작업 실패는 기록한 뒤 다시 전달한다.
"""Coordinate chat persistence, durable memory work, and provider calls."""

from __future__ import annotations

import asyncio
from math import isfinite

from app.db.transaction import use_case_transaction
from app.db.types import SessionFactory
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.query import messages as MessagesQueryService
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.llm import types as LLMTypes


def _memory_sources(
    value: Types.MemorySourceInfo,
) -> tuple[MemoryTypes.SourceMessageInfo, ...]:
    if value.truncated:
        raise RuntimeError("Memory source safety limit was exceeded.")
    return tuple(
        MemoryTypes.SourceMessageInfo(
            id=item.id,
            sender_type=item.sender_type,
            content=item.content,
            position=item.position,
            revision=item.revision,
        )
        for item in value.messages
    )


# claim된 작업의 미완성 색인을 먼저 처리하고 필요한 요약을 생성한다. 오류 종류에 따라 큐의 실패/재시도를 기록한다.
async def process_memory_work(
    session_factory: SessionFactory,
    command: Types.ProcessMemoryWorkCommand,
    *,
    summary_generator: MemoryService.SummaryGenerator,
    indexer: MemoryService.MemoryIndexer,
) -> None:
    """Process one fixed work generation without holding DB state across I/O."""
    if (
        isinstance(command.timeout_seconds, bool)
        or not isfinite(command.timeout_seconds)
        or command.timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be positive and finite.")
    work, policy, models = command.work, command.policy, command.models
    try:
        try:
            async with asyncio.timeout(command.timeout_seconds) as timeout:
                await _process_memory_work(
                    session_factory,
                    work,
                    policy=policy,
                    models=models,
                    summary_generator=summary_generator,
                    indexer=indexer,
                    deadline=timeout,
                )
                _check_work_deadline(timeout)
        except TimeoutError as exc:
            if timeout.expired():
                raise MemoryTypes.MemoryWorkDeadlineExceededError(
                    "Memory work exceeded its total processing deadline."
                ) from exc
            raise
    except Exception as exc:
        retryable = (
            isinstance(exc, (LLMTypes.LLMError, LLMTypes.EmbeddingError))
            and exc.retryable
        )
        if isinstance(exc, (TimeoutError, ConnectionError)):
            retryable = True
        async with session_factory() as session:
            await MemoryService.fail_memory_work(
                session,
                MemoryTypes.FailMemoryWorkCommand(
                    work=work,
                    error_kind=_error_kind(exc),
                    retryable=retryable,
                ),
            )
        raise


def _check_work_deadline(deadline: asyncio.Timeout | None) -> None:
    # A client may suppress cancellation or spend time in synchronous parsing.
    # Reject a late result before starting the next persistence/provider step.
    if deadline is None:
        return
    expires_at = deadline.when()
    # Timer callbacks can run within the loop's clock resolution before when().
    # Once cancellation fired, a provider that suppressed it still lost its budget.
    if deadline.expired() or (
        expires_at is not None and asyncio.get_running_loop().time() >= expires_at
    ):
        raise MemoryTypes.MemoryWorkDeadlineExceededError(
            "Memory work exceeded its total processing deadline."
        )


def _error_kind(exc: Exception) -> str:
    kind = getattr(exc, "kind", None)
    return getattr(kind, "value", None) or type(exc).__name__


async def _process_memory_work(
    session_factory: SessionFactory,
    work: MemoryTypes.MemoryWorkInfo,
    *,
    policy: MemoryTypes.MemoryPolicy,
    models: MemoryTypes.MemoryModelConfig,
    summary_generator: MemoryService.SummaryGenerator,
    indexer: MemoryService.MemoryIndexer,
    deadline: asyncio.Timeout | None = None,
) -> None:
    pending = await _read_pending_index(session_factory, work)
    _check_work_deadline(deadline)
    if pending is not None:
        await _index_summary(
            session_factory, work, pending, models, indexer, deadline=deadline
        )

    conversation, messages, has_more = await _read_unsummarized(
        session_factory, work, policy=policy
    )
    _check_work_deadline(deadline)
    plan = MemoryService.plan_summarization(
        MemoryTypes.PlanSummarizationCommand(
            conversation_id=work.conversation_id,
            owner_id=work.owner_id,
            conversation_revision=conversation.history_revision,
            messages=messages,
            policy=policy,
            summary_through_position=work.summary_through_position,
        )
    )
    _check_work_deadline(deadline)
    if plan is None:
        await _complete(session_factory, work, more_work=False)
        return

    generated = await summary_generator.generate_summary(
        MemoryTypes.GenerateSummaryCommand(
            plan=plan,
            provider=models.summary_provider,
            model=models.summary_model,
            max_output_tokens=policy.summary_output_tokens,
        )
    )
    _check_work_deadline(deadline)
    summary = await _persist_summary(
        session_factory, generated, work=work, deadline=deadline
    )
    _check_work_deadline(deadline)
    await _index_summary(
        session_factory, work, summary, models, indexer, deadline=deadline
    )

    remaining = tuple(
        item for item in messages if item.position > plan.source_end_position
    )
    more_work = has_more or (
        MemoryService.plan_summarization(
            MemoryTypes.PlanSummarizationCommand(
                conversation_id=work.conversation_id,
                owner_id=work.owner_id,
                conversation_revision=conversation.history_revision,
                messages=remaining,
                policy=policy,
                summary_through_position=work.summary_through_position,
            )
        )
        is not None
    )
    _check_work_deadline(deadline)
    await _complete(session_factory, work, more_work=more_work)


async def _read_pending_index(
    session_factory: SessionFactory, work: MemoryTypes.MemoryWorkInfo
) -> MemoryTypes.MemoryInfo | None:
    async with session_factory() as session:
        return await MemoryService.get_pending_index(
            session,
            MemoryTypes.GetPendingIndexCommand(
                conversation_id=work.conversation_id, owner_id=work.owner_id
            ),
        )


async def _read_unsummarized(
    session_factory: SessionFactory,
    work: MemoryTypes.MemoryWorkInfo,
    *,
    policy: MemoryTypes.MemoryPolicy,
) -> tuple[
    ConversationTypes.ConversationInfo, tuple[MemoryTypes.SourceMessageInfo, ...], bool
]:
    async with session_factory() as session, use_case_transaction(session):
        conversation = await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=work.conversation_id, user_id=work.owner_id, lock=True
            ),
        )
        latest = await MemoryService.get_latest_summary(
            session,
            MemoryTypes.GetLatestSummaryCommand(
                conversation_id=work.conversation_id, owner_id=work.owner_id
            ),
        )
        after = (
            latest.source_end_position if latest and latest.source_end_position else 0
        )
        # A batch-sized prefix decides work/threshold; the real suffix protects
        # recent text even when a large middle range is intentionally not loaded.
        prefix = await MessagesQueryService.read_message_window(
            session,
            Types.ReadMessageWindowCommand(
                conversation_id=work.conversation_id,
                user_id=work.owner_id,
                after_position=after,
                token_budget=max(
                    policy.summarization_threshold_tokens, policy.summary_batch_tokens
                )
                + policy.recent_raw_tokens,
                newest_first=False,
            ),
        )
        by_position = {item.position: item for item in prefix.messages}
        if prefix.has_more:
            tail = await MessagesQueryService.read_message_window(
                session,
                Types.ReadMessageWindowCommand(
                    conversation_id=work.conversation_id,
                    user_id=work.owner_id,
                    after_position=after,
                    token_budget=policy.recent_raw_tokens,
                ),
            )
            by_position.update((item.position, item) for item in tail.messages)
        source = Types.MemorySourceInfo(
            tuple(by_position[position] for position in sorted(by_position)), False
        )
        return conversation, _memory_sources(source), prefix.has_more


async def _persist_summary(
    session_factory: SessionFactory,
    generated: MemoryTypes.GeneratedSummaryInfo,
    *,
    work: MemoryTypes.MemoryWorkInfo,
    deadline: asyncio.Timeout | None = None,
) -> MemoryTypes.MemoryInfo:
    plan = generated.plan
    async with session_factory() as session, use_case_transaction(session):
        conversation = await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=plan.conversation_id,
                user_id=plan.owner_id,
                lock=True,
            ),
        )
        source = await MessagesQueryService.read_message_window(
            session,
            Types.ReadMessageWindowCommand(
                conversation_id=plan.conversation_id,
                user_id=plan.owner_id,
                after_position=plan.source_start_position - 1,
                through_position=plan.source_end_position,
                token_budget=plan.estimated_input_tokens,
                newest_first=False,
            ),
        )
        if source.has_more:
            raise MemoryTypes.StaleMemoryWorkError("Summary source range changed.")
        MemoryService.validate_summary_source(
            MemoryTypes.ValidateSummarySourceCommand(
                plan=plan,
                current_messages=_memory_sources(
                    Types.MemorySourceInfo(source.messages, source.has_more)
                ),
                current_conversation_revision=conversation.history_revision,
            )
        )
        _check_work_deadline(deadline)
        return await MemoryService.save_summary(
            session, MemoryTypes.SaveSummaryCommand(generated=generated, work=work)
        )


async def _index_summary(
    session_factory: SessionFactory,
    work: MemoryTypes.MemoryWorkInfo,
    summary: MemoryTypes.MemoryInfo,
    models: MemoryTypes.MemoryModelConfig,
    indexer: MemoryService.MemoryIndexer,
    *,
    deadline: asyncio.Timeout | None = None,
) -> None:
    _check_work_deadline(deadline)
    if summary.conversation_revision is None:
        raise MemoryTypes.StaleMemoryWorkError(
            "Legacy memory cannot be indexed as a summary."
        )
    digest = MemoryService.content_digest(summary.content)
    embedded = await indexer.embed_summary(
        MemoryTypes.EmbedSummaryCommand(
            memory_id=summary.id,
            conversation_id=work.conversation_id,
            owner_id=work.owner_id,
            content=summary.content,
            content_digest=digest,
            conversation_revision=summary.conversation_revision,
            provider=models.embedding_provider,
            model=models.embedding_model,
            output_dimension=models.embedding_output_dimension,
        )
    )
    _check_work_deadline(deadline)
    async with session_factory() as session, use_case_transaction(session):
        conversation = await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=work.conversation_id,
                user_id=work.owner_id,
                lock=True,
            ),
        )
        if conversation.history_revision != summary.conversation_revision:
            raise MemoryTypes.StaleMemoryWorkError("History changed during indexing.")
        _check_work_deadline(deadline)
        await MemoryService.save_summary_embedding(
            session, MemoryTypes.SaveEmbeddingCommand(value=embedded, work=work)
        )


async def _complete(
    session_factory: SessionFactory,
    work: MemoryTypes.MemoryWorkInfo,
    *,
    more_work: bool,
) -> None:
    async with session_factory() as session:
        await MemoryService.complete_memory_work(
            session,
            MemoryTypes.CompleteMemoryWorkCommand(work=work, more_work=more_work),
        )
