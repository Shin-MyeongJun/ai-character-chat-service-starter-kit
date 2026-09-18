# 답변 저장과 기억 예약을 조합하고, 워커에서는 읽기 → 외부 요약/임베딩 → 잠금 후 재검증을 수행한다.
# 외부 호출 성공 뒤 DB 저장이 실패할 수 있으며 작업 실패는 기록한 뒤 다시 전달한다.
"""Coordinate chat persistence, durable memory work, and provider calls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.llm import types as LLMTypes


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryModelConfig:
    summary_provider: LLMTypes.LLMProvider | str | None
    summary_model: str
    embedding_provider: LLMTypes.EmbeddingProvider | str | None
    embedding_model: str
    embedding_output_dimension: int | None = None


def _memory_sources(
    value: ChatTypes.MemorySourceInfo,
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


# 성공 생성 저장과 기억 작업 예약을 같은 트랜잭션으로 묶는다. 완료 재전송은 세대를 다시 올리지 않는다.
async def finish_generation_and_schedule_memory(
    session, command: ChatTypes.FinishGenerationCommand
) -> ChatTypes.GenerationInfo:
    """The successful response and queue generation commit atomically."""
    async with use_case_transaction(session):
        before = await ChatService.get_generation_state(
            session,
            ChatTypes.GetGenerationStateCommand(
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
        before = await ChatService.get_generation_state(
            session,
            ChatTypes.GetGenerationStateCommand(
                generation_id=command.generation_id, user_id=command.user_id
            ),
        )
        result = await ChatService.finish_generation(session, command)
        if result.status == "succeeded" and before.status == "pending":
            generation = await ChatService.get_generation_state(
                session,
                ChatTypes.GetGenerationStateCommand(
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


# claim된 작업의 미완성 색인을 먼저 처리하고 필요한 요약을 생성한다. 오류 종류에 따라 큐의 실패/재시도를 기록한다.
async def process_memory_work(
    session_factory: Callable,
    work: MemoryTypes.MemoryWorkInfo,
    *,
    policy: MemoryTypes.MemoryPolicy,
    models: MemoryModelConfig,
    summary_generator: MemoryService.SummaryGenerator,
    indexer: MemoryService.MemoryIndexer,
) -> None:
    """Process one fixed work generation without holding DB state across I/O."""
    try:
        await _process_memory_work(
            session_factory,
            work,
            policy=policy,
            models=models,
            summary_generator=summary_generator,
            indexer=indexer,
        )
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


def _error_kind(exc: Exception) -> str:
    kind = getattr(exc, "kind", None)
    return getattr(kind, "value", None) or type(exc).__name__


async def _process_memory_work(
    session_factory: Callable,
    work: MemoryTypes.MemoryWorkInfo,
    *,
    policy: MemoryTypes.MemoryPolicy,
    models: MemoryModelConfig,
    summary_generator: MemoryService.SummaryGenerator,
    indexer: MemoryService.MemoryIndexer,
) -> None:
    pending = await _read_pending_index(session_factory, work)
    if pending is not None:
        await _index_summary(session_factory, work, pending, models, indexer)

    conversation, messages = await _read_unsummarized(session_factory, work)
    plan = MemoryService.plan_summarization(
        MemoryTypes.PlanSummarizationCommand(
            conversation_id=work.conversation_id,
            owner_id=work.owner_id,
            conversation_revision=conversation.history_revision,
            messages=messages,
            policy=policy,
        )
    )
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
    summary = await _persist_summary(session_factory, generated)
    await _index_summary(session_factory, work, summary, models, indexer)

    remaining = tuple(
        item for item in messages if item.position > plan.source_end_position
    )
    more_work = (
        MemoryService.plan_summarization(
            MemoryTypes.PlanSummarizationCommand(
                conversation_id=work.conversation_id,
                owner_id=work.owner_id,
                conversation_revision=conversation.history_revision,
                messages=remaining,
                policy=policy,
            )
        )
        is not None
    )
    await _complete(session_factory, work, more_work=more_work)


async def _read_pending_index(session_factory, work):
    async with session_factory() as session:
        return await MemoryService.get_pending_index(
            session,
            MemoryTypes.GetPendingIndexCommand(
                conversation_id=work.conversation_id, owner_id=work.owner_id
            ),
        )


async def _read_unsummarized(session_factory, work):
    async with session_factory() as session:
        conversation = await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=work.conversation_id, user_id=work.owner_id
            ),
        )
        latest = await MemoryService.get_latest_summary(
            session,
            MemoryTypes.GetLatestSummaryCommand(
                conversation_id=work.conversation_id, owner_id=work.owner_id
            ),
        )
        source = await ChatService.list_memory_source(
            session,
            ChatTypes.ListMemorySourceCommand(
                conversation_id=work.conversation_id,
                user_id=work.owner_id,
                after_position=latest.source_end_position
                if latest and latest.source_end_position
                else 0,
            ),
        )
        return conversation, _memory_sources(source)


async def _persist_summary(session_factory, generated):
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
        source = await ChatService.list_memory_source(
            session,
            ChatTypes.ListMemorySourceCommand(
                conversation_id=plan.conversation_id,
                user_id=plan.owner_id,
                after_position=plan.source_start_position - 1,
                through_position=plan.source_end_position,
            ),
        )
        MemoryService.validate_summary_source(
            MemoryTypes.ValidateSummarySourceCommand(
                plan=plan,
                current_messages=_memory_sources(source),
                current_conversation_revision=conversation.history_revision,
            )
        )
        return await MemoryService.save_summary(
            session, MemoryTypes.SaveSummaryCommand(generated=generated)
        )


async def _index_summary(session_factory, work, summary, models, indexer):
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
        await MemoryService.save_summary_embedding(
            session, MemoryTypes.SaveEmbeddingCommand(value=embedded)
        )


async def _complete(session_factory, work, *, more_work):
    async with session_factory() as session:
        await MemoryService.complete_memory_work(
            session,
            MemoryTypes.CompleteMemoryWorkCommand(work=work, more_work=more_work),
        )
