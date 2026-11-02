"""U01: durable compaction requests, real summaries and successful answer retries."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_memory_claim_fencing import claim, expire, seed_conversation
from test_memory_query import embedding_service
from test_nonstream_answers import setup_answer

from app.db.models.chat import Message
from app.db.models.memory import ConversationMemory, MemoryJob
from app.db.models.product_usage import ProductGeneration
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.workflow.memory import process_memory_work
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as Types
from app.modules.chatting.prompt import service as PromptService
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.llm import types as LLMTypes

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("content", ["x" * 800, "한" * 300])
async def test_forced_plan_bypasses_threshold_and_keeps_recent_sources(
    content: str,
) -> None:
    messages = tuple(
        Types.SourceMessageInfo(uuid4(), "user", content, i + 1, 1) for i in range(11)
    )
    policy = Types.MemoryPolicy(summary_batch_tokens=300)
    target = MemoryService.plan_context_compaction(
        Types.PlanContextCompactionCommand(
            messages=messages,
            policy=policy,
            available_tokens=5800,
            conservative_token_budget=True,
        )
    )
    command = Types.PlanSummarizationCommand(
        conversation_id=uuid4(),
        owner_id=uuid4(),
        conversation_revision=1,
        messages=messages,
        policy=policy,
    )
    assert MemoryService.plan_summarization(command) is None
    plans = []
    while messages and messages[0].position <= target:
        plan = MemoryService.plan_summarization(
            replace(command, messages=messages, summary_through_position=target)
        )
        assert plan is not None
        plans.append(plan)
        messages = tuple(i for i in messages if i.position > plan.source_end_position)
    assert len(plans) > 1
    assert messages[-1] == command.messages[-1]
    assert (
        sum(
            MemoryService.estimate_message_tokens(
                i.sender_type, i.content, conservative=True
            )
            for i in messages
        )
        <= 5800
    )


@pytest.mark.parametrize(
    "content,raw_budget,recent_tokens,batch_tokens,fixed_extra",
    [
        pytest.param("x" * 800, 5800, 1200, 3000, 0, id="ascii"),
        pytest.param("한" * 300, 6500, 1200, 3000, 0, id="korean"),
        pytest.param("x" * 200, 650, 100, 150, 0, id="small-window-multiple-batches"),
        pytest.param("한" * 100, 1000, 150, 200, 5000, id="large-fixed-context"),
    ],
)
async def test_summary_request_compacts_then_same_input_answer_succeeds(
    db: AsyncSession,
    content: str,
    raw_budget: int,
    recent_tokens: int,
    batch_tokens: int,
    fixed_extra: int,
) -> None:
    orchestrator, command, text = await setup_answer(db)
    if fixed_extra:
        orchestrator.template = replace(
            orchestrator.template,
            role_rules=(*orchestrator.template.role_rules, "f" * fixed_extra),
        )
    history = []
    for index in range(11):
        history.append(
            await ChatService.create_message(
                db,
                ChatTypes.CreateMessageCommand(
                    conversation_id=command.conversation_id,
                    user_id=command.user_id,
                    request_key=f"history-{index}",
                    content=content,
                ),
            )
        )
    current = await ChatService.create_message(
        db,
        ChatTypes.CreateMessageCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            request_key="current-input",
            content="Continue with these facts.",
        ),
    )
    command = replace(
        command, input_message_id=current.id, expected_revision=current.revision
    )
    async with use_case_transaction(db):
        runtime = await ConversationService.prepare_runtime_context(
            db,
            ConversationTypes.PrepareRuntimeContextCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                activation_text=current.content,
            ),
        )
    base = PromptService.build_prompt(
        PromptTypes.BuildPromptCommand(
            template=orchestrator.template,
            runtime=runtime,
            product_character_id=command.product_character_id,
            current_message=PromptTypes.PromptMessageInfo(
                current.id, current.sender_type, current.content, current.position
            ),
        )
    )
    policy = Types.MemoryPolicy(
        recent_raw_tokens=recent_tokens, summary_batch_tokens=batch_tokens
    )
    orchestrator.config = replace(
        orchestrator.config,
        max_prompt_tokens=base.estimated_tokens + 1200 + raw_budget,
        memory_policy=policy,
    )
    assert orchestrator.config.max_prompt_tokens < 32000
    embedding = embedding_service()
    orchestrator.retriever = MemoryService.MemoryRetriever(
        orchestrator.sessions, embedding
    )

    first = await orchestrator.generate_answer(command)
    assert (
        first.status == "failed"
        and first.error_code == "summary_required"
        and first.retryable
    )
    text.generate_text.assert_not_awaited()
    async with db.begin():
        job = await db.scalar(select(MemoryJob))
        target = job.summary_through_position
        assert target is not None and target < current.position
        assert await db.scalar(select(func.count()).select_from(Message)) == 13
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProductGeneration)
                .where(ProductGeneration.status == "pending")
            )
            == 0
        )

    summary_text = SimpleNamespace(
        generate_text=AsyncMock(
            return_value=LLMTypes.LLMResultInfo(
                "Earlier facts retained.",
                LLMTypes.LLMProvider.MOCK,
                "summary",
                LLMTypes.TokenUsageInfo(100, 10, 110),
                status="completed",
            )
        )
    )
    generator = MemoryService.SummaryGenerator(summary_text)
    indexer = MemoryService.MemoryIndexer(embedding)
    batches = 0
    while (
        work := await MemoryService.claim_memory_work(
            db, Types.ClaimMemoryWorkCommand(worker_id="u01")
        )
    ) is not None:
        assert work.summary_through_position == target
        await process_memory_work(
            orchestrator.sessions,
            ChatTypes.ProcessMemoryWorkCommand(
                work,
                policy,
                Types.MemoryModelConfig(
                    summary_provider="mock",
                    summary_model="summary",
                    embedding_provider="voyage",
                    embedding_model="voyage-large-2",
                ),
            ),
            summary_generator=generator,
            indexer=indexer,
        )
        batches += 1
        assert batches < 20
    assert batches >= 1
    if batch_tokens < 3000:
        assert batches > 1
    async with db.begin():
        summaries = (
            await db.scalars(
                select(ConversationMemory).order_by(
                    ConversationMemory.source_end_position
                )
            )
        ).all()
        assert len(summaries) == batches
        assert summaries[-1].source_end_position >= target
        assert all(
            i.index_status == "ready" and i.source_end_position < current.position
            for i in summaries
        )
        assert await db.scalar(select(func.count()).select_from(Message)) == 13
        job = await db.get(MemoryJob, command.conversation_id, populate_existing=True)
        assert job.status == "idle" and job.summary_through_position is None

    # A request key is a durable outcome. The retry uses the same saved input
    # and a new answer key, as the answer API already requires.
    assert await orchestrator.generate_answer(command) == first
    answer = await orchestrator.generate_answer(
        replace(command, request_key="after-compaction")
    )
    assert answer.status == "succeeded", answer
    text.generate_text.assert_awaited_once()
    request_json = text.generate_text.await_args.args[0].request_json
    prompt = json.loads(request_json)
    assert (
        sum(len(i["content"].encode()) + 32 for i in prompt["messages"]) + 32 + 1200
        <= orchestrator.config.max_prompt_tokens
    )
    assert request_json.count(current.content) == 1
    references = json.loads(prompt["messages"][1]["content"])["reference_data"]
    assert "Earlier facts retained." in references["memories"]
    raw_history = prompt["messages"][2:-1]
    assert len(raw_history) < 12
    assert any(i["content"] == history[-1].content for i in raw_history)
    async with db.begin():
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.sender_type == "user")
            )
            == 13
        )


async def test_target_survives_new_requests_reclaim_and_stale_completion(
    db: AsyncSession,
) -> None:
    cid, owner_id = await seed_conversation(db)

    async def schedule(target: int | None) -> None:
        await MemoryService.schedule_memory_work(
            db,
            Types.ScheduleMemoryWorkCommand(
                conversation_id=cid, owner_id=owner_id, summary_through_position=target
            ),
        )

    await schedule(10)
    previous = await claim(db)
    assert previous.summary_through_position == 10
    await schedule(20)
    await schedule(None)
    await schedule(5)
    await expire(db, cid)
    current = await claim(db)
    assert (
        current.summary_through_position == 20
        and previous.claim_token != current.claim_token
    )
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=previous)
    )
    await MemoryService.fail_memory_work(
        db,
        Types.FailMemoryWorkCommand(
            work=current, retryable=True, error_kind="transient"
        ),
    )
    async with db.begin():
        await db.execute(
            update(MemoryJob).values(
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=60)
            )
        )
    retried = await claim(db)
    assert retried.summary_through_position == 20
    await schedule(30)
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=retried)
    )
    next_work = await claim(db)
    assert next_work.summary_through_position == 30
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=next_work, more_work=True)
    )
    next_batch = await claim(db)
    assert next_batch.summary_through_position == 30
    await MemoryService.complete_memory_work(
        db, Types.CompleteMemoryWorkCommand(work=next_batch)
    )
    async with db.begin():
        job = await db.get(MemoryJob, cid, populate_existing=True)
        assert job.status == "idle" and job.summary_through_position is None


async def test_impossible_protected_target_fails_explicitly() -> None:
    source = (Types.SourceMessageInfo(uuid4(), "user", "x" * 800, 1, 1),)
    with pytest.raises(Types.ContextCompactionUnavailableError):
        MemoryService.plan_context_compaction(
            Types.PlanContextCompactionCommand(
                messages=source,
                policy=Types.MemoryPolicy(),
                available_tokens=100,
                conservative_token_budget=True,
            )
        )
    with pytest.raises(Types.ContextCompactionUnavailableError):
        MemoryService.plan_summarization(
            Types.PlanSummarizationCommand(
                conversation_id=uuid4(),
                owner_id=uuid4(),
                conversation_revision=1,
                messages=source,
                policy=Types.MemoryPolicy(),
                summary_through_position=1,
            )
        )


async def test_protected_history_overflow_is_terminal_without_queue_or_text_call(
    db: AsyncSession,
) -> None:
    orchestrator, command, text = await setup_answer(db)
    for index, content in enumerate(("x" * 16000, "Continue.")):
        current = await ChatService.create_message(
            db,
            ChatTypes.CreateMessageCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                request_key=f"protected-{index}",
                content=content,
            ),
        )
    answer = await orchestrator.generate_answer(
        replace(
            command, input_message_id=current.id, expected_revision=current.revision
        )
    )
    assert answer.status == "failed"
    assert answer.error_code == "fixed_context_exceeded" and not answer.retryable
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0


async def test_worker_records_impossible_target_as_failure_instead_of_idle(
    db: AsyncSession,
) -> None:
    cid, owner_id = await seed_conversation(db)
    async with db.begin():
        target = await db.scalar(select(func.min(Message.position)))
    await MemoryService.schedule_memory_work(
        db,
        Types.ScheduleMemoryWorkCommand(
            conversation_id=cid, owner_id=owner_id, summary_through_position=target
        ),
    )
    work = await claim(db)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    generator = SimpleNamespace(generate_summary=AsyncMock())
    indexer = SimpleNamespace(embed_summary=AsyncMock())
    with pytest.raises(Types.ContextCompactionUnavailableError):
        await process_memory_work(
            factory,
            ChatTypes.ProcessMemoryWorkCommand(
                work,
                Types.MemoryPolicy(),
                Types.MemoryModelConfig(
                    summary_provider="mock",
                    summary_model="summary",
                    embedding_provider="voyage",
                    embedding_model="voyage-large-2",
                ),
            ),
            summary_generator=generator,
            indexer=indexer,
        )
    generator.generate_summary.assert_not_awaited()
    indexer.embed_summary.assert_not_awaited()
    async with db.begin():
        job = await db.get(MemoryJob, cid, populate_existing=True)
        assert job.status == "failed" and job.summary_through_position == target
        assert job.last_error_kind == "ContextCompactionUnavailableError"
