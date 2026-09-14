from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.db.models.chat import Conversation
from app.db.models.identity import User
from app.db.models.memory import MemoryJob
from app.db.models.product import Product
from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.memory.service.command.indexing import (
    MemoryIndexer,
    content_digest,
)
from app.modules.chatting.memory.service.command.summarization import (
    SummaryGenerator,
    plan_summarization,
    validate_summary_source,
)
from app.modules.chatting.memory.service.query.retrieval import _select_memories
from app.modules.llm import types as LLMTypes
from app.use_cases import memory as MemoryUseCase
from app.use_cases.answer_preparation import (
    PrepareAnswerContextCommand,
    prepare_answer_context,
)
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


def messages(count=8, size=40):
    return tuple(
        MemoryTypes.SourceMessageInfo(
            uuid4(),
            "user" if index % 2 == 0 else "character",
            ("not agreed " if index == 0 else "detail ") + "x" * size,
            index + 1,
            1,
        )
        for index in range(count)
    )


def runtime_view():
    return ConversationTypes.ConversationRuntimeView(
        execution=LLMTypes.ExecutionView(
            model_id=uuid4(),
            provider="mock",
            model="mock-model",
            reasoning_effort="none",
            replacement=False,
            scheduled_at=None,
        ),
        product_snapshot_id=str(uuid4()),
        settings={},
        start=ConversationTypes.RuntimeStart(title="", content=""),
        characters=[],
        lorebooks=[],
    )


class SessionFactory:
    class Context:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    def __call__(self):
        return self.Context()


def chat_message(position: int, content: str):
    return SimpleNamespace(
        id=uuid4(),
        conversation_id=uuid4(),
        sender_type="user" if position % 2 else "character",
        content=content,
        position=position,
        revision=1,
    )


async def test_summary_trigger_uses_unsummarized_message_size_and_keeps_recent_raw():
    source = messages()
    policy = MemoryTypes.MemoryPolicy(
        summarization_threshold_tokens=80,
        summary_batch_tokens=50,
        recent_raw_tokens=30,
    )
    plan = plan_summarization(
        MemoryTypes.PlanSummarizationCommand(
            conversation_id=uuid4(),
            owner_id=uuid4(),
            conversation_revision=3,
            messages=source,
            policy=policy,
        )
    )
    assert plan is not None
    assert 0 < len(plan.source_messages) < len(source)
    assert plan.source_messages[0] == source[0]
    assert plan.source_end_position < source[-1].position
    assert plan.estimated_input_tokens <= policy.summary_batch_tokens

    below = plan_summarization(
        MemoryTypes.PlanSummarizationCommand(
            conversation_id=uuid4(),
            owner_id=uuid4(),
            conversation_revision=1,
            messages=source[:1],
            policy=policy,
        )
    )
    assert below is None


async def test_summary_prompt_preserves_user_text_and_tracks_provider_usage():
    plan = MemoryTypes.SummaryPlanInfo(
        conversation_id=uuid4(),
        owner_id=uuid4(),
        conversation_revision=1,
        source_messages=messages(2),
        source_digest="digest",
        estimated_input_tokens=20,
        prompt_version="hypha-summary-v1",
    )
    service = SimpleNamespace(
        generate_text=AsyncMock(
            return_value=LLMTypes.LLMResultInfo(
                content="The user did not agree.",
                provider=LLMTypes.LLMProvider.MOCK,
                model="mock-summary",
                usage=LLMTypes.TokenUsageInfo(input_tokens=21, output_tokens=7),
            )
        )
    )
    result = await SummaryGenerator(service).generate_summary(
        MemoryTypes.GenerateSummaryCommand(
            plan=plan, provider="mock", model="mock-summary", max_output_tokens=100
        )
    )
    request = service.generate_text.await_args.args[0]
    assert "user: not agreed" in request.request_json
    assert result.content == "The user did not agree."
    assert (result.input_tokens, result.output_tokens) == (21, 7)


async def test_source_revision_or_message_change_rejects_stale_summary():
    source = messages(2)
    plan = MemoryTypes.SummaryPlanInfo(uuid4(), uuid4(), 2, source, "wrong", 20, "v1")
    with pytest.raises(MemoryTypes.StaleMemoryWorkError):
        validate_summary_source(
            MemoryTypes.ValidateSummarySourceCommand(
                plan=plan,
                current_messages=source,
                current_conversation_revision=3,
            )
        )
    with pytest.raises(MemoryTypes.StaleMemoryWorkError):
        validate_summary_source(
            MemoryTypes.ValidateSummarySourceCommand(
                plan=plan,
                current_messages=source[:-1],
                current_conversation_revision=2,
            )
        )


async def test_indexing_uses_document_purpose_and_rejects_bad_dimension():
    good = LLMTypes.EmbeddingResultInfo(
        embeddings=(tuple([1.0] * 1536),),
        dimension=1536,
        provider=LLMTypes.EmbeddingProvider.VOYAGE,
        model="voyage-large-2",
        usage=LLMTypes.EmbeddingUsageInfo(total_tokens=9),
    )
    service = SimpleNamespace(embed_texts=AsyncMock(return_value=good))
    content = "durable summary"
    command = MemoryTypes.EmbedSummaryCommand(
        memory_id=uuid4(),
        conversation_id=uuid4(),
        owner_id=uuid4(),
        content=content,
        content_digest=content_digest(content),
        conversation_revision=4,
        provider="voyage",
        model="voyage-large-2",
    )
    result = await MemoryIndexer(service).embed_summary(command)
    request = service.embed_texts.await_args.args[0]
    assert request.purpose is LLMTypes.EmbeddingPurpose.DOCUMENT
    assert result.total_tokens == 9

    service.embed_texts.return_value = LLMTypes.EmbeddingResultInfo(
        embeddings=(tuple([1.0] * 1024),),
        dimension=1024,
        provider=LLMTypes.EmbeddingProvider.VOYAGE,
        model="voyage-4",
        usage=LLMTypes.EmbeddingUsageInfo(total_tokens=5),
    )
    with pytest.raises(ValueError, match="incompatible"):
        await MemoryIndexer(service).embed_summary(command)


async def test_embedding_retry_reuses_pending_summary_without_regeneration(monkeypatch):
    conversation_id, owner_id = uuid4(), uuid4()
    pending = MemoryTypes.MemoryInfo(
        id=uuid4(),
        conversation_id=conversation_id,
        memory_type="summary",
        content="already generated",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        conversation_revision=1,
    )
    embedding_failure = LLMTypes.EmbeddingError(
        "timeout",
        kind=LLMTypes.EmbeddingErrorKind.TIMEOUT,
        provider=LLMTypes.EmbeddingProvider.VOYAGE,
        model="voyage-large-2",
        retryable=True,
    )
    index_summary = AsyncMock(side_effect=[embedding_failure, None])
    read_unsummarized = AsyncMock(
        return_value=(SimpleNamespace(history_revision=1), messages(1, 1))
    )
    complete = AsyncMock()
    monkeypatch.setattr(
        MemoryUseCase, "_read_pending_index", AsyncMock(return_value=pending)
    )
    monkeypatch.setattr(MemoryUseCase, "_index_summary", index_summary)
    monkeypatch.setattr(MemoryUseCase, "_read_unsummarized", read_unsummarized)
    monkeypatch.setattr(MemoryUseCase, "_complete", complete)
    generator = SimpleNamespace(generate_summary=AsyncMock())
    work = MemoryTypes.MemoryWorkInfo(
        conversation_id=conversation_id,
        owner_id=owner_id,
        scope_generation=1,
        attempt_count=1,
        lease_owner="worker-a",
    )
    factory = SessionFactory()
    policy = MemoryTypes.MemoryPolicy()
    models = MemoryUseCase.MemoryModelConfig(
        summary_provider="mock",
        summary_model="mock-summary",
        embedding_provider="voyage",
        embedding_model="voyage-large-2",
    )

    with pytest.raises(LLMTypes.EmbeddingError):
        await MemoryUseCase._process_memory_work(
            factory,
            work,
            policy=policy,
            models=models,
            summary_generator=generator,
            indexer=object(),
        )
    read_unsummarized.assert_not_awaited()

    await MemoryUseCase._process_memory_work(
        factory,
        work,
        policy=policy,
        models=models,
        summary_generator=generator,
        indexer=object(),
    )
    assert index_summary.await_count == 2
    generator.generate_summary.assert_not_awaited()
    complete.assert_awaited_once_with(factory, work, more_work=False)


async def test_selection_deduplicates_and_returns_stable_chronological_order():
    now = datetime.now(UTC)
    first_id, duplicate_id, second_id = uuid4(), uuid4(), uuid4()
    candidates = [
        MemoryTypes.RetrievedMemoryInfo(
            first_id,
            "summary",
            "same fact",
            0.8,
            created_at=now - timedelta(days=1),
            source_end_position=20,
        ),
        MemoryTypes.RetrievedMemoryInfo(
            duplicate_id,
            "summary",
            " SAME FACT ",
            0.7,
            created_at=now,
            source_end_position=10,
        ),
        MemoryTypes.RetrievedMemoryInfo(
            second_id,
            "event",
            "other",
            0.9,
            importance=0.8,
            created_at=now,
            source_end_position=30,
        ),
    ]
    selected = _select_memories(candidates, 100, now=now)
    assert [item.memory_id for item in selected] == [first_id, second_id]
    assert all(item.estimated_tokens > 0 for item in selected)


async def test_durable_queue_coalesces_requests_arriving_during_a_lease(db):
    owner = User(id=uuid4(), email=f"hypha-{uuid4()}@test.local")
    product = Product(id=uuid4(), owner_id=owner.id, title="Hypha")
    conversation = Conversation(id=uuid4(), user_id=owner.id, product_id=product.id)
    async with use_case_transaction(db):
        db.add(owner)
        await db.flush()
        db.add(product)
        await db.flush()
        db.add(conversation)
        await db.flush()

    command = MemoryTypes.ScheduleMemoryWorkCommand(
        conversation_id=conversation.id, owner_id=owner.id
    )
    await MemoryService.schedule_memory_work(db, command)
    await MemoryService.schedule_memory_work(db, command)
    work = await MemoryService.claim_memory_work(
        db, MemoryTypes.ClaimMemoryWorkCommand(worker_id="worker-a", lease_seconds=60)
    )
    assert work is not None and work.scope_generation == 2

    await MemoryService.schedule_memory_work(db, command)
    await MemoryService.complete_memory_work(
        db, MemoryTypes.CompleteMemoryWorkCommand(work=work)
    )
    row = await db.scalar(
        select(MemoryJob).where(MemoryJob.conversation_id == conversation.id)
    )
    assert row.status == "pending"
    assert row.completed_generation == 2
    assert row.requested_generation == 3


async def test_answer_context_never_drops_unsummarized_messages(monkeypatch):
    conversation_id, owner_id = uuid4(), uuid4()
    runtime = runtime_view()
    source = SimpleNamespace(
        truncated=False,
        messages=(
            chat_message(1, "summarized"),
            chat_message(2, "new user fact"),
            chat_message(3, "new reply"),
        ),
    )
    latest = MemoryTypes.MemoryInfo(
        id=uuid4(),
        conversation_id=conversation_id,
        memory_type="summary",
        content="old summary",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        index_status="ready",
        source_start_position=1,
        source_end_position=1,
    )
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.ConversationService.prepare_runtime_context",
        AsyncMock(return_value=runtime),
    )
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.MemoryService.get_latest_summary",
        AsyncMock(return_value=latest),
    )
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.ChatService.list_memory_source",
        AsyncMock(return_value=source),
    )
    retriever = SimpleNamespace(retrieve_memories=AsyncMock(return_value=[]))
    result = await prepare_answer_context(
        SessionFactory(),
        PrepareAnswerContextCommand(
            conversation_id=conversation_id,
            owner_id=owner_id,
            current_message="current",
            max_prompt_tokens=2000,
            response_tokens=200,
            embedding_model="voyage-large-2",
        ),
        memory_retriever=retriever,
    )
    assert [item.position for item in result.recent_messages][-2:] == [2, 3]
    assert result.current_message == "current"
    assert (
        sum(
            (
                result.budget.base,
                result.budget.memories,
                result.budget.recent_messages,
                result.budget.current_message,
                result.budget.response_reserve,
            )
        )
        <= result.budget.maximum
    )


async def test_answer_context_fails_explicitly_when_unsummarized_text_cannot_fit(
    monkeypatch,
):
    conversation_id, owner_id = uuid4(), uuid4()
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.ConversationService.prepare_runtime_context",
        AsyncMock(return_value=runtime_view()),
    )
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.MemoryService.get_latest_summary",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.use_cases.answer_preparation.ChatService.list_memory_source",
        AsyncMock(
            return_value=SimpleNamespace(
                truncated=False, messages=(chat_message(1, "x" * 4000),)
            )
        ),
    )
    retriever = SimpleNamespace(retrieve_memories=AsyncMock(return_value=[]))
    with pytest.raises(MemoryTypes.ContextBudgetExceededError) as caught:
        await prepare_answer_context(
            SessionFactory(),
            PrepareAnswerContextCommand(
                conversation_id=conversation_id,
                owner_id=owner_id,
                current_message="current",
                max_prompt_tokens=300,
                response_tokens=100,
                embedding_model="voyage-large-2",
            ),
            memory_retriever=retriever,
        )
    assert caught.value.summary_required is True
    retriever.retrieve_memories.assert_not_awaited()
