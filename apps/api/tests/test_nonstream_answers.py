# PostgreSQL과 mock 공급자로 중복 요청·취소·결과 staging 실패·복구를 검증한다. 외부 호출 중 대화 잠금도 검사한다.
"""Real PostgreSQL orchestration with mocked external text/embedding calls."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.db.models.billing import UsageLog
from app.db.models.chat import Message
from app.db.models.memory import MemoryJob
from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.llm import types as LLMTypes
from app.use_cases import answers as Answers
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_product_usage import scenario

pytestmark = pytest.mark.asyncio


def result(content='"반가워요, 선배님."'):
    return LLMTypes.LLMResultInfo(
        content,
        LLMTypes.LLMProvider.OPENAI,
        "gpt-test",
        LLMTypes.TokenUsageInfo(100, 30, 130),
        status="completed",
        finish_reason="completed",
    )


async def setup_answer(db, *, config=None):
    from app.db.models.model_routing import Model, Provider

    owner, _product, _release, cid, character_id = await scenario(db)
    async with db.begin():
        await db.execute(update(Provider).values(name="openai"))
        await db.execute(update(Model).values(model_name="gpt-test"))
    current = await ChatService.create_message(
        db,
        ChatTypes.CreateMessageCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="input-1",
            content="선배님, 같이 갈까요?",
        ),
    )
    command = Answers.GenerateAnswerCommand(
        conversation_id=cid,
        user_id=owner.id,
        request_key="answer-1",
        input_message_id=current.id,
        expected_revision=current.revision,
        product_character_id=character_id,
    )
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    text = SimpleNamespace(generate_text=AsyncMock(return_value=result()))
    retriever = SimpleNamespace(retrieve_memories=AsyncMock(return_value=[]))
    orchestrator = Answers.AnswerOrchestrator(sessions, text, retriever, config=config)
    return orchestrator, command, text


async def test_success_replay_is_one_answer_usage_and_memory_job(db):
    orchestrator, command, text = await setup_answer(db)
    first = await orchestrator.generate_answer(command)
    assert first.status == "succeeded" and first.content == result().content
    assert await orchestrator.generate_answer(command) == first
    assert text.generate_text.await_count == 1
    prompt = text.generate_text.await_args.args[0].request_json
    assert prompt.count("선배님, 같이 갈까요?") == 1
    async with db.begin():
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.sender_type == "user")
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 1
        )
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1
        job = await db.scalar(select(MemoryJob))
        assert job.requested_generation == 1
        run = await db.get(ProductGeneration, first.generation_id)
        assert run.answer_metadata["template"]["digest"] == orchestrator.template.digest
        assert run.answer_metadata["usage"]["input_tokens"] == 100


async def test_pending_concurrent_and_conflicting_requests(db):
    orchestrator, command, text = await setup_answer(db)
    entered, release = asyncio.Event(), asyncio.Event()

    async def generate(_):
        entered.set()
        await release.wait()
        return result()

    text.generate_text.side_effect = generate
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        assert (await orchestrator.generate_answer(command)).status == "pending"
        with pytest.raises(ChatTypes.MessageConflictError):
            await orchestrator.generate_answer(
                replace(command, product_character_id=uuid4())
            )
        with pytest.raises(ChatTypes.MessageConflictError):
            await orchestrator.generate_answer(
                replace(command, request_key="other-key")
            )
    finally:
        release.set()
    assert (await task).status == "succeeded"
    assert text.generate_text.await_count == 1


async def test_foreign_owner_and_invalid_input_rejected_before_provider(db):
    orchestrator, command, text = await setup_answer(db)
    with pytest.raises(LookupError):
        await orchestrator.generate_answer(replace(command, user_id=uuid4()))
    with pytest.raises(ChatTypes.MessageConflictError):
        await orchestrator.generate_answer(replace(command, input_message_id=uuid4()))
    with pytest.raises(ValueError):
        await orchestrator.generate_answer(
            replace(command, product_character_id=uuid4())
        )
    text.generate_text.assert_not_awaited()


@pytest.mark.parametrize(
    "kind,uncertain",
    [
        (LLMTypes.LLMErrorKind.AUTHENTICATION, False),
        (LLMTypes.LLMErrorKind.RATE_LIMIT, False),
        (LLMTypes.LLMErrorKind.TIMEOUT, True),
        (LLMTypes.LLMErrorKind.CONNECTION, True),
    ],
)
async def test_provider_failure_is_terminal_and_never_automatically_recalled(
    db, kind, uncertain
):
    orchestrator, command, text = await setup_answer(db)
    text.generate_text.side_effect = LLMTypes.LLMError(
        "private provider text",
        kind=kind,
        provider=LLMTypes.LLMProvider.OPENAI,
        model="gpt-test",
        retryable=True,
    )
    first = await orchestrator.generate_answer(command)
    assert first.status == "failed" and first.error_code == "llm_" + kind.value
    assert first.uncertain is uncertain
    assert (await orchestrator.generate_answer(command)) == first
    assert text.generate_text.await_count == 1
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1


@pytest.mark.parametrize(
    "bad_result,code",
    [
        (result(" "), "empty_response"),
        (replace(result(), finish_reason="max_output_tokens"), "invalid_result"),
        (replace(result(), usage=LLMTypes.TokenUsageInfo(None, 5)), "invalid_usage"),
    ],
)
async def test_invalid_outputs_do_not_save_success(db, bad_result, code):
    orchestrator, command, text = await setup_answer(db)
    text.generate_text.return_value = bad_result
    answer = await orchestrator.generate_answer(command)
    assert answer.status == "failed" and answer.error_code == code
    async with db.begin():
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 0
        )


async def test_cancel_releases_pending_and_does_not_repeat(db):
    orchestrator, command, text = await setup_answer(db)
    entered = asyncio.Event()

    async def hang(_):
        entered.set()
        await asyncio.Future()

    text.generate_text.side_effect = hang
    task = asyncio.create_task(orchestrator.generate_answer(command))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    replay = await orchestrator.generate_answer(command)
    assert replay.status == "cancelled" and replay.uncertain
    assert text.generate_text.await_count == 1


async def test_result_storage_failure_recovers_without_provider_or_duplicate_usage(
    db, monkeypatch
):
    orchestrator, command, text = await setup_answer(db)
    original = Answers.finish_generation_and_schedule_memory
    monkeypatch.setattr(
        Answers,
        "finish_generation_and_schedule_memory",
        AsyncMock(side_effect=RuntimeError("storage down")),
    )
    with pytest.raises(Answers.AnswerStorageError):
        await orchestrator.generate_answer(command)
    async with db.begin():
        run = await db.scalar(select(ProductGeneration))
        assert run.answer_metadata["phase"] == "result_ready"
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 0
        await db.execute(
            update(ProductGeneration).values(
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    monkeypatch.setattr(Answers, "finish_generation_and_schedule_memory", original)
    assert await orchestrator.recover_answers() == 1
    assert await orchestrator.recover_answers() == 0
    assert (await orchestrator.generate_answer(command)).status == "succeeded"
    assert text.generate_text.await_count == 1
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1


async def test_interrupted_call_is_failed_on_recovery(db, monkeypatch):
    orchestrator, command, text = await setup_answer(db)
    original_stage = orchestrator._stage

    async def interrupted_stage(generation_id, user_id, metadata, lease):
        if metadata["phase"] == "result_ready":
            raise RuntimeError("database disconnected before staging result")
        await original_stage(generation_id, user_id, metadata, lease)

    monkeypatch.setattr(orchestrator, "_stage", interrupted_stage)
    with pytest.raises(Answers.AnswerStorageError):
        await orchestrator.generate_answer(command)
    async with db.begin():
        await db.execute(
            update(ProductGeneration).values(
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert await orchestrator.recover_answers() == 1
    replay = await orchestrator.generate_answer(command)
    assert replay.status == "failed" and replay.error_code == "interrupted_uncertain"
    assert text.generate_text.await_count == 1


async def test_summary_required_finishes_pending_before_scheduling_memory(
    db, monkeypatch
):
    orchestrator, command, text = await setup_answer(db)
    from app.modules.chatting.memory.types import ContextBudgetExceededError

    monkeypatch.setattr(
        Answers,
        "prepare_answer_context",
        AsyncMock(
            side_effect=ContextBudgetExceededError("wait", summary_required=True)
        ),
    )
    answer = await orchestrator.generate_answer(command)
    assert (
        answer.status == "failed"
        and answer.retryable
        and answer.error_code == "summary_required"
    )
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProductGeneration)
                .where(ProductGeneration.status == "pending")
            )
            == 0
        )


async def test_fixed_context_exceeded_without_call_or_memory_job(db):
    orchestrator, command, text = await setup_answer(
        db, config=Answers.AnswerConfig(max_prompt_tokens=200, response_tokens=100)
    )
    answer = await orchestrator.generate_answer(command)
    assert answer.error_code == "fixed_context_exceeded" and not answer.retryable
    text.generate_text.assert_not_awaited()
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(MemoryJob)) == 0


async def test_model_is_pinned_and_external_call_holds_no_conversation_lock(db):
    from app.db.models.chat import Conversation
    from app.db.models.model_routing import Model

    orchestrator, command, text = await setup_answer(db)

    async def generate(value):
        # NOWAIT would fail if the request still held its reservation lock.
        async with orchestrator.sessions() as session, session.begin():
            await session.scalar(
                select(Conversation)
                .where(Conversation.id == command.conversation_id)
                .with_for_update(nowait=True)
            )
            run = await session.scalar(select(ProductGeneration))
            await session.execute(
                update(Model)
                .where(Model.id == run.model_id)
                .values(model_name="gpt-new-config")
            )
            assert value.model == run.model_name and value.model != "gpt-new-config"
        return result()

    text.generate_text.side_effect = generate
    first = await orchestrator.generate_answer(command)
    assert first.status == "succeeded" and first.model != "gpt-new-config"
    orchestrator.template = replace(
        orchestrator.template, digest="different-deployment-template"
    )
    assert await orchestrator.generate_answer(command) == first
    assert text.generate_text.await_count == 1


async def test_memory_failure_rolls_back_answer_and_usage_then_recovers(
    db, monkeypatch
):
    from app.use_cases import memory as MemoryUseCase

    orchestrator, command, text = await setup_answer(db)
    original = MemoryUseCase.MemoryService.schedule_memory_work
    monkeypatch.setattr(
        MemoryUseCase.MemoryService,
        "schedule_memory_work",
        AsyncMock(side_effect=RuntimeError("queue insert failed")),
    )
    with pytest.raises(Answers.AnswerStorageError):
        await orchestrator.generate_answer(command)
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 0
        )
        assert (await db.scalar(select(ProductGeneration))).status == "pending"
        await db.execute(
            update(ProductGeneration).values(
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    monkeypatch.setattr(MemoryUseCase.MemoryService, "schedule_memory_work", original)
    await asyncio.gather(orchestrator.recover_answers(), orchestrator.recover_answers())
    assert (await orchestrator.generate_answer(command)).status == "succeeded"
    assert text.generate_text.await_count == 1
    async with db.begin():
        assert (await db.scalar(select(MemoryJob))).requested_generation == 1
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1


async def test_http_to_postgres_returns_one_persisted_answer(db):
    import httpx
    from app.http.answers import get_answer_orchestrator, router
    from app.http.dependencies import get_current_owner_id
    from fastapi import FastAPI

    orchestrator, command, text = await setup_answer(db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = lambda: command.user_id
    app.dependency_overrides[get_answer_orchestrator] = lambda: orchestrator
    body = {
        "request_key": command.request_key,
        "input_message_id": str(command.input_message_id),
        "expected_revision": command.expected_revision,
        "product_character_id": str(command.product_character_id),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            f"/conversations/{command.conversation_id}/answers", json=body
        )
        second = await client.post(
            f"/conversations/{command.conversation_id}/answers", json=body
        )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["content"] == result().content
    assert text.generate_text.await_count == 1
