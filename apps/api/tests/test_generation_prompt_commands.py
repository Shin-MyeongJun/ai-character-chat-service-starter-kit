"""Run prompt command validation and real mappers with storage/transaction doubles."""

import hashlib
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import prompts as PromptsCommandService
from app.modules.chatting.chat.service.query import prompts as PromptsQueryService


@pytest.fixture
def prompt_command(monkeypatch):
    now = datetime.now(UTC)
    raw = '{ "messages": [{"role":"system","content":"고정 지침 🌏\\n"}], "chat_message_format":1 }'
    digest = hashlib.sha256(raw.encode()).hexdigest()
    command = Types.SaveGenerationPromptCommand(
        generation_id=uuid4(),
        user_id=uuid4(),
        execution_token=str(uuid4()),
        request_json=raw,
        provider="openai",
        max_output_tokens=1200,
    )
    metadata = {
        "execution_token": command.execution_token,
        "prompt_digest": digest,
        "provider": "openai",
        "response_tokens": 1200,
        "phase": "reserved",
    }
    run = Types.GenerationStateInfo(
        command.generation_id,
        command.user_id,
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        "gpt-test",
        "none",
        "request-key",
        "input",
        None,
        "pending",
        0,
        None,
        metadata,
        now + timedelta(minutes=1),
    )

    @asynccontextmanager
    async def transaction(session):
        yield

    monkeypatch.setattr(PromptsCommandService, "use_case_transaction", transaction)
    monkeypatch.setattr(
        PromptsCommandService.ConversationService, "get_owned_conversation", AsyncMock()
    )
    get_run = AsyncMock(return_value=run)
    get_prompt = AsyncMock(return_value=None)
    create = AsyncMock()
    monkeypatch.setattr(
        PromptsCommandService.PromptsRepository, "get_owned_generation", get_run
    )
    monkeypatch.setattr(
        PromptsCommandService.PromptsRepository, "get_generation_prompt", get_prompt
    )
    monkeypatch.setattr(
        PromptsCommandService.PromptsRepository, "create_generation_prompt", create
    )
    return SimpleNamespace(
        command=command,
        run=run,
        now=now,
        digest=digest,
        get_run=get_run,
        get_prompt=get_prompt,
        create=create,
    )


@pytest.mark.asyncio
async def test_command_stores_exact_utf8_digest_and_only_approved_execution_fields(
    prompt_command,
):
    item = prompt_command
    session = object()
    await PromptsCommandService.save_generation_prompt(session, item.command)
    args, kwargs = item.create.await_args
    assert args == (session, item.command.generation_id)
    assert kwargs == {
        "request_json": item.command.request_json,
        "digest": item.digest,
        "format_version": 1,
        "provider": "openai",
        "max_output_tokens": 1200,
    }
    assert item.get_run.await_args.kwargs == {"lock": True}


@pytest.mark.asyncio
async def test_identical_replay_keeps_original_record_and_timestamp_even_after_completion(
    prompt_command,
):
    item = prompt_command
    item.get_run.return_value = replace(item.run, status="succeeded")
    item.get_prompt.return_value = SimpleNamespace(
        request_json=item.command.request_json,
        digest=item.digest,
        created_at=item.now,
        format_version=1,
        provider="openai",
        max_output_tokens=1200,
    )
    await PromptsCommandService.save_generation_prompt(object(), item.command)
    item.create.assert_not_awaited()
    assert item.get_prompt.return_value.created_at == item.now


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"request_json": "different"},
        {"execution_token": "other"},
        {"provider": "anthropic"},
        {"max_output_tokens": 600},
    ],
)
async def test_command_rejects_prompt_or_execution_snapshot_changes(
    prompt_command, change
):
    item = prompt_command
    with pytest.raises(Types.MessageConflictError):
        await PromptsCommandService.save_generation_prompt(
            object(), replace(item.command, **change)
        )
    item.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"status": "failed"},
        {"answer_lease_until": None},
        {"answer_lease_until": datetime(2020, 1, 1, tzinfo=UTC)},
        {"answer_metadata": {}},
    ],
)
async def test_command_cannot_create_record_outside_live_reservation(
    prompt_command, change
):
    item = prompt_command
    item.get_run.return_value = replace(item.run, **change)
    with pytest.raises(Types.MessageConflictError):
        await PromptsCommandService.save_generation_prompt(object(), item.command)
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_record_with_different_bytes_cannot_be_overwritten(
    prompt_command,
):
    item = prompt_command
    item.get_prompt.return_value = SimpleNamespace(
        request_json=item.command.request_json + " ",
        digest=item.digest,
        created_at=item.now,
        format_version=1,
        provider="openai",
        max_output_tokens=1200,
    )
    with pytest.raises(Types.MessageConflictError, match="immutable"):
        await PromptsCommandService.save_generation_prompt(object(), item.command)
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_public_original_query_requires_admin_before_repository(monkeypatch):
    from contextlib import nullcontext

    identity = AsyncMock(side_effect=LookupError("not admin"))
    query = AsyncMock()
    monkeypatch.setattr(
        PromptsQueryService.IdentityQueryService, "require_admin", identity
    )
    monkeypatch.setattr(
        PromptsQueryService.PromptsRepository, "get_generation_prompt_summary", query
    )
    session = SimpleNamespace(no_autoflush=nullcontext())
    with pytest.raises(LookupError):
        await PromptsQueryService.get_generation_prompt(
            session, Types.GetGenerationPromptCommand(uuid4(), uuid4())
        )
    query.assert_not_awaited()
