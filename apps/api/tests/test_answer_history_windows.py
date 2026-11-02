"""U05: real PostgreSQL history windows, change detection and query volume."""

from collections import defaultdict
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, select, update, func
from test_memory_query import embedding_service
from test_hypha_memory import runtime_view
from test_lorebook_activation_contracts import keyword_entry
from test_nonstream_answers import setup_answer

from app.db.models.chat import Message, Conversation, ConversationCharacter
from app.db.models.memory import ConversationMemory, MemoryJob
from app.db.models.model_routing import Model
from app.db.models.product_usage import ProductGeneration
from app.db.models.credit import CreditReservation
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.chatting.chat.service.query import messages as Messages
from app.modules.chatting.chat.service.workflow import answer_preparation as Preparation
from app.modules.chatting.chat.service.workflow.memory import process_memory_work
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.content.lorebook.service.activation import diagnose_entries
from app.modules.llm import types as LLMTypes

pytestmark = pytest.mark.asyncio


async def seed_history(db, count, *, summarized=True):
    orchestrator, command, text = await setup_answer(db)
    async with db.begin():
        positions = list(
            await db.scalars(
                insert(Message).returning(Message.position),
                [
                    dict(
                        conversation_id=command.conversation_id,
                        sender_type="user",
                        content=f"fact {index:05d}",
                    )
                    for index in range(count)
                ],
            )
        )
        if summarized:
            db.add(
                ConversationMemory(
                    conversation_id=command.conversation_id,
                    memory_type="summary",
                    content="Earlier facts.",
                    source_start_position=1,
                    source_end_position=max(positions),
                    conversation_revision=1,
                )
            )
    current = await ChatService.create_message(
        db,
        Types.CreateMessageCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            request_key="current",
            content="Continue.",
        ),
    )
    return orchestrator, replace(command, input_message_id=current.id), text


@pytest.mark.parametrize("count", [1000, 10050])
async def test_history_query_volume(db, monkeypatch, count):
    orchestrator, command, text = await seed_history(db, count)
    phase = "other"
    statements = defaultdict(list)
    preparation = orchestrator._read_preparation
    context = Answers.prepare_answer_context

    def record(_conn, cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements[phase].append(("FROM messages" in statement, cursor.rowcount))

    async def read(*args, **kwargs):
        nonlocal phase
        phase = "preparation" if "preparation" not in statements else "revalidation"
        try:
            return await preparation(*args, **kwargs)
        finally:
            phase = "other"

    async def prepare(*args, **kwargs):
        nonlocal phase
        phase = "context"
        try:
            return await context(*args, **kwargs)
        finally:
            phase = "other"

    monkeypatch.setattr(orchestrator, "_read_preparation", read)
    monkeypatch.setattr(Answers, "prepare_answer_context", prepare)
    event.listen(db.bind.sync_engine, "after_cursor_execute", record)
    try:
        answer = await orchestrator.generate_answer(command)
    finally:
        event.remove(db.bind.sync_engine, "after_cursor_execute", record)
    assert answer.status == "succeeded"
    assert await orchestrator.generate_answer(command) == answer
    text.generate_text.assert_awaited_once()
    for name, values in statements.items():
        print(name, "selects", len(values), "message_rows", sum(n for msg, n in values if msg))
    for name in ("preparation", "revalidation"):
        assert sum(n for msg, n in statements[name] if msg) <= 102
    assert sum(n for msg, n in statements["context"] if msg) <= 258


async def test_long_unsummarized_history_compacts_and_retries_same_input(db):
    orchestrator, command, text = await seed_history(db, 10500, summarized=False)
    policy = MemoryTypes.MemoryPolicy(
        summarization_threshold_tokens=11000, summary_batch_tokens=10000,
        recent_raw_tokens=100,
    )
    orchestrator.config = replace(orchestrator.config, memory_policy=policy)
    first = await orchestrator.generate_answer(command)
    assert first.status == "failed" and first.error_code == "summary_required"
    assert await orchestrator.generate_answer(command) == first
    text.generate_text.assert_not_awaited()
    async with db.begin():
        target = await db.scalar(select(MemoryJob.summary_through_position))
        assert target and target > 10000
        assert await db.scalar(select(func.count()).select_from(CreditReservation)) == 0
    embedding = embedding_service()
    summary_text = SimpleNamespace(generate_text=AsyncMock(return_value=LLMTypes.LLMResultInfo(
        "Earlier facts retained.", LLMTypes.LLMProvider.MOCK, "summary",
        LLMTypes.TokenUsageInfo(100, 10, 110), status="completed",
    )))
    generator = MemoryService.SummaryGenerator(summary_text)
    indexer = MemoryService.MemoryIndexer(embedding)
    plans = []
    generate = generator.generate_summary

    async def record_plan(request):
        plans.append(request.plan)
        return await generate(request)

    generator.generate_summary = record_plan
    while work := await MemoryService.claim_memory_work(
        db, MemoryTypes.ClaimMemoryWorkCommand(worker_id="u05")
    ):
        await process_memory_work(
            orchestrator.sessions,
            Types.ProcessMemoryWorkCommand(
                work, policy, MemoryTypes.MemoryModelConfig(
                    summary_provider="mock", summary_model="summary",
                    embedding_provider="voyage", embedding_model="voyage-large-2",
                ),
            ),
            summary_generator=generator, indexer=indexer,
        )
        assert len(plans) < 12
    assert 1 < len(plans) < 12
    summarized_positions = [item.position for plan in plans for item in plan.source_messages]
    assert summarized_positions == list(range(1, target + 1))
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(Message)) == 10502
        assert await db.scalar(select(MemoryJob.status)) == "idle"
        assert await db.scalar(select(MemoryJob.summary_through_position)) is None
    orchestrator.retriever = MemoryService.MemoryRetriever(orchestrator.sessions, embedding)
    retry = replace(command, request_key="same-input-after-summary")
    answer = await orchestrator.generate_answer(retry)
    assert answer.status == "succeeded"
    assert await orchestrator.generate_answer(retry) == answer
    text.generate_text.assert_awaited_once()


@pytest.mark.parametrize("change", ["edit", "rewind", "append", "old_content", "model", "participant", "runtime", "snapshot"])
async def test_preparation_mutations_conflict_before_billing(db, change):
    orchestrator, command, text = await seed_history(db, 160)
    entered, release = asyncio.Event(), asyncio.Event()

    async def retrieve(_request):
        entered.set()
        await release.wait()
        return []

    orchestrator.retriever.retrieve_memories.side_effect = retrieve
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        if change == "edit":
            await ChatService.replace_message(db, Types.ReplaceMessageCommand(
                conversation_id=command.conversation_id, user_id=command.user_id,
                message_id=command.input_message_id, expected_revision=1, content="changed",
            ))
        elif change == "rewind":
            await ChatService.rewind_messages(db, Types.RewindMessagesCommand(
                conversation_id=command.conversation_id, user_id=command.user_id,
                message_id=command.input_message_id,
            ))
        elif change == "append":
            await ChatService.create_message(db, Types.CreateMessageCommand(
                conversation_id=command.conversation_id, user_id=command.user_id,
                request_key="concurrent-append", content="new input",
            ))
        else:
            async with db.begin():
                if change == "old_content":
                    # Outside the lore/prompt tail; no application revision bump.
                    await db.execute(update(Message).where(Message.position == 1).values(content="rewritten"))
                elif change == "model":
                    await db.execute(update(Model).values(context_window=31000))
                elif change == "participant":
                    await db.execute(update(ConversationCharacter).values(role_order=7))
                elif change == "runtime":
                    from app.db.models.snapshot import ProductSnapshot
                    snapshot = await db.scalar(select(ProductSnapshot))
                    snapshot.snapshot_data = dict(snapshot.snapshot_data, prompt="changed runtime prompt")
                else:
                    # This field is part of conversation snapshot identity even
                    # when the selected runtime/current snapshot is unchanged.
                    await db.execute(update(Conversation).values(opening_mode="legacy_messages"))
    finally:
        release.set()
    with pytest.raises(Types.MessageConflictError):
        await task
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(ProductGeneration)) == 0
        assert await db.scalar(select(func.count()).select_from(CreditReservation)) == 0


async def test_change_between_initial_read_and_context_does_not_consume_key(db, monkeypatch):
    orchestrator, command, text = await seed_history(db, 160)
    prepare = Answers.prepare_answer_context

    async def change_then_prepare(*args, **kwargs):
        async with db.begin():
            await db.execute(update(Message).where(Message.position == 1).values(content="changed"))
        return await prepare(*args, **kwargs)

    monkeypatch.setattr(Answers, "prepare_answer_context", change_then_prepare)
    with pytest.raises(Types.MessageConflictError):
        await orchestrator.generate_answer(command)
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(ProductGeneration)) == 0


@pytest.mark.parametrize("conservative", [False, True])
@pytest.mark.parametrize("summarized", [False, True])
async def test_bounded_context_matches_full_history_reference(db, monkeypatch, conservative, summarized):
    orchestrator, command, _ = await seed_history(db, 1000, summarized=summarized)
    async with db.begin():
        entities = (await db.scalars(select(Message).order_by(Message.position))).all()
        all_messages = tuple(PersistenceMapper.message_entity_to_info(row) for row in entities)
    request = Types.PrepareAnswerContextCommand(
        conversation_id=command.conversation_id, owner_id=command.user_id,
        current_message="Continue.", current_message_id=command.input_message_id,
        max_prompt_tokens=2000, response_tokens=200, embedding_model="test",
        runtime=runtime_view(), rendered_base_tokens=100 if conservative else None,
        policy=MemoryTypes.MemoryPolicy(recent_raw_tokens=100),
    )

    async def outcome():
        try:
            return await Preparation.prepare_answer_context(
                orchestrator.sessions, request, memory_retriever=orchestrator.retriever
            )
        except MemoryTypes.ContextBudgetExceededError as error:
            return type(error), error.summary_required, error.summary_through_position

    bounded = await outcome()
    bounded_calls = orchestrator.retriever.retrieve_memories.call_args_list[:]
    orchestrator.retriever.retrieve_memories.reset_mock()
    monkeypatch.setattr(Messages, "read_message_window", AsyncMock(return_value=Types.MessageWindowInfo(all_messages, False)))
    assert await outcome() == bounded
    assert orchestrator.retriever.retrieve_memories.call_args_list == bounded_calls


async def test_lore_tail_covers_maximum_depth_and_preserves_legacy_text_rule(db):
    orchestrator, command, _ = await seed_history(db, 160)
    async with use_case_transaction(db):
        recent = await Messages.list_recent_messages(db, Types.ListRecentMessagesCommand(
            conversation_id=command.conversation_id, user_id=command.user_id,
        ))
    assert len(recent) == 100
    messages = tuple((item.sender_type, item.content) for item in recent)
    included = keyword_entry("contains", [recent[0].content], {"scan_depth": 100})
    excluded = keyword_entry("contains", ["fact 00000"], {"scan_depth": 100})
    legacy = keyword_entry("contains", [recent[0].content], None)
    _, diagnostics = diagnose_entries([included, excluded, legacy], text="Continue.", messages=messages)
    assert {item["id"]: item["included"] for item in diagnostics} == {
        included["id"]: True, excluded["id"]: False, legacy["id"]: False,
    }

