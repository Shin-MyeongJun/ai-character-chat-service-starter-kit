"""Exercise the real answer workflow with isolated transaction/service boundaries."""

import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.llm import types as LLMTypes
from test_nonstream_answers import result


@pytest.fixture
def workflow(monkeypatch):
    events, saved = [], []
    transaction_active = False
    raw = '{ "chat_message_format": 1, "messages": [{"role":"system","content":"지침\\n"},{"role":"user","content":"현재 입력"}] }'

    @asynccontextmanager
    async def sessions():
        yield object()

    @asynccontextmanager
    async def transaction(session):
        nonlocal transaction_active
        transaction_active = True
        events.append("begin")
        try:
            yield
        except BaseException:
            events.append("rollback")
            raise
        else:
            events.append("commit")
        finally:
            transaction_active = False

    async def store(session, command):
        assert transaction_active
        events.append("save_prompt")
        saved.append(command)

    async def generate(command):
        assert not transaction_active
        assert events[-2:] == ["commit", "stage:calling"]
        events.append("external_call")
        assert saved[0].request_json == command.request_json == raw
        assert (
            hashlib.sha256(command.request_json.encode()).hexdigest()
            == metadata["prompt_digest"]
        )
        return result()

    async def stage(generation_id, user_id, value, lease):
        events.append("stage:" + value["phase"])

    metadata = {}

    async def update(session, command):
        metadata.update(command.metadata)

    text = SimpleNamespace(generate_text=AsyncMock(side_effect=generate))
    pricing = SimpleNamespace(price_book=object())
    orchestrator = Answers.AnswerOrchestrator(sessions, text, object(), pricing=pricing)
    execution = LLMTypes.ExecutionView(
        uuid4(), "openai", "gpt-test", "none", False, None
    )
    current = SimpleNamespace(id=uuid4(), revision=1, content="현재 입력")
    runtime = SimpleNamespace(execution=execution, product_snapshot_id=str(uuid4()))
    prepared = (
        current,
        runtime,
        SimpleNamespace(context_window=8000),
        SimpleNamespace(product_id=uuid4()),
        "snapshot",
    )
    command = Types.GenerateAnswerCommand(
        conversation_id=uuid4(),
        user_id=uuid4(),
        request_key="answer-key",
        input_message_id=current.id,
        expected_revision=1,
        product_character_id=uuid4(),
    )
    run = SimpleNamespace(id=uuid4(), model_name="gpt-test", reasoning_effort="none")
    monkeypatch.setattr(Answers, "use_case_transaction", transaction)
    monkeypatch.setattr(orchestrator, "_get_request", AsyncMock(return_value=None))
    monkeypatch.setattr(
        orchestrator, "_read_preparation", AsyncMock(return_value=prepared)
    )
    monkeypatch.setattr(
        Answers.PromptMapper, "message_info_to_prompt", lambda value: value
    )
    monkeypatch.setattr(
        Answers.PromptService,
        "build_prompt",
        lambda value: PromptTypes.PromptInfo(raw, 100),
    )
    monkeypatch.setattr(
        Answers,
        "prepare_answer_context",
        AsyncMock(return_value=SimpleNamespace(recent_messages=(), memories=())),
    )
    monkeypatch.setattr(
        Answers.GenerationCommandService,
        "begin_generation",
        AsyncMock(return_value=run),
    )
    monkeypatch.setattr(
        Answers.BillingQuoteService,
        "create_billing_quote",
        AsyncMock(return_value=SimpleNamespace(id=uuid4())),
    )
    monkeypatch.setattr(
        Answers.BillingCreditService,
        "reserve_credit",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), reserved_credit=10)),
    )
    monkeypatch.setattr(Answers.AnswersCommandService, "update_answer", update)
    monkeypatch.setattr(
        Answers.PromptsCommandService,
        "save_generation_prompt",
        AsyncMock(side_effect=store),
    )
    monkeypatch.setattr(orchestrator, "_stage", stage)
    answer = Types.AnswerInfo(
        run.id, "succeeded", result().content, "gpt-test", None, False, False, 10
    )
    monkeypatch.setattr(
        orchestrator, "_complete_staged", AsyncMock(return_value=answer)
    )
    return SimpleNamespace(
        orchestrator=orchestrator,
        command=command,
        text=text,
        events=events,
        saved=saved,
        answer=answer,
    )


@pytest.mark.asyncio
async def test_prompt_store_participates_in_reservation_commit_before_call(workflow):
    value = workflow
    assert await value.orchestrator.generate_answer(value.command) == value.answer
    assert len(value.saved) == 1
    assert (
        value.saved[0].provider == "openai" and value.saved[0].max_output_tokens == 1200
    )


@pytest.mark.asyncio
async def test_prompt_failure_rolls_back_reservation_scope_and_blocks_call(
    workflow, monkeypatch
):
    async def fail(session, command):
        workflow.events.append("save_failed")
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(Answers.PromptsCommandService, "save_generation_prompt", fail)
    with pytest.raises(
        Types.AnswerStorageError, match="Reservation storage is uncertain"
    ):
        await workflow.orchestrator.generate_answer(workflow.command)
    workflow.text.generate_text.assert_not_awaited()
    assert "rollback" in workflow.events


@pytest.mark.asyncio
async def test_lost_reservation_commit_ack_never_repeats_external_call(
    workflow, monkeypatch
):
    count = 0
    transaction = Answers.use_case_transaction

    @asynccontextmanager
    async def lost_commit(session):
        nonlocal count
        count += 1
        async with transaction(session):
            yield
        if count == 2:
            raise RuntimeError("commit acknowledgement lost")

    existing = SimpleNamespace(id=workflow.answer.generation_id)
    monkeypatch.setattr(Answers, "use_case_transaction", lost_commit)
    monkeypatch.setattr(
        workflow.orchestrator,
        "_get_request",
        AsyncMock(side_effect=[None, None, existing]),
    )
    resumed = Types.AnswerInfo(
        existing.id, "pending", None, "gpt-test", None, False, False, 10
    )
    monkeypatch.setattr(
        workflow.orchestrator, "_resume", AsyncMock(return_value=resumed)
    )
    assert await workflow.orchestrator.generate_answer(workflow.command) == resumed
    workflow.text.generate_text.assert_not_awaited()
    assert len(workflow.saved) == 1
