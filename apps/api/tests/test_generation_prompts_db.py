"""Real PostgreSQL prompt durability, billing rollback, replay, history mutation and recovery."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.db.models.billing_quote import BillingQuote
from app.db.models.credit import CreditReservation
from app.db.models.generation_prompt import GenerationPrompt
from app.db.models.identity import User
from app.db.models.model_routing import Model, Provider
from app.db.models.product_usage import ProductGeneration
from app.http.dependencies import get_current_owner_id, get_product_session
from app.main import create_app
from app.modules.chatting.chat import service as ChatService
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.command import prompts as PromptsCommandService
from app.modules.chatting.chat.service.query import prompts as PromptsQueryService
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.llm import types as LLMTypes
from app.modules.reporting.operations_reporting import types as OperationsTypes
from app.modules.reporting.operations_reporting.service import (
    prompts as OperationsPromptsService,
)
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from test_answer_billing_integration import check_state
from test_nonstream_answers import result, setup_answer

pytestmark = pytest.mark.asyncio


async def make_admin(db):
    async with db.begin():
        admin = User(email=f"{uuid4()}@example.test", role="admin", status="active")
        db.add(admin)
        await db.flush()
        return admin.id


async def read_prompt(orchestrator):
    async with orchestrator.sessions() as session:
        return (await session.scalars(select(GenerationPrompt))).one()


async def test_exact_prompt_digest_and_execution_are_committed_before_external_call(db):
    orchestrator, command, text = await setup_answer(db)
    admin = await make_admin(db)
    observed = []

    async def generate(value):
        # An independent connection sees the row and can acquire its lock. Flush alone cannot pass.
        async with orchestrator.sessions() as session, session.begin():
            prompt = (
                await session.scalars(
                    select(GenerationPrompt).with_for_update(nowait=True)
                )
            ).one()
            run = await session.get(ProductGeneration, prompt.generation_id)
            assert prompt.request_json == value.request_json
            assert (
                prompt.digest
                == hashlib.sha256(value.request_json.encode("utf-8")).hexdigest()
            )
            assert prompt.digest == run.answer_metadata["prompt_digest"]
            assert prompt.provider == value.provider
            assert prompt.max_output_tokens == value.max_output_tokens
            assert prompt.format_version == 1
            assert run.status == "pending" and run.answer_metadata["phase"] == "calling"
            assert run.model_name == value.model
            assert (
                None if run.reasoning_effort == "none" else run.reasoning_effort
            ) == value.reasoning_effort
            assert "request_json" not in run.answer_metadata
            observed.append((prompt.request_json, prompt.digest, prompt.created_at))
        return result()

    text.generate_text.side_effect = generate
    answer = await orchestrator.generate_answer(command)
    stored = await read_prompt(orchestrator)
    assert answer.status == "succeeded"
    assert observed == [(stored.request_json, stored.digest, stored.created_at)]
    async with orchestrator.sessions() as session:
        view = await OperationsPromptsService.get_generation_prompt(
            session,
            OperationsTypes.GetGenerationPromptCommand(answer.generation_id),
            actor=OperationsTypes.ActorCommand(admin),
        )
        assert view.prompt.request_json == stored.request_json
    # Model catalog changes cannot rewrite execution history.
    async with db.begin():
        await db.execute(update(Model).values(model_name="renamed-after-generation"))
        await db.execute(update(Provider).values(name="renamed-provider"))
    async with orchestrator.sessions() as session:
        info = await PromptsQueryService.get_generation_prompt(
            session, ChatTypes.GetGenerationPromptCommand(admin, answer.generation_id)
        )
        assert (
            info.generation.model_name == "gpt-test"
            and info.prompt.provider == "openai"
        )


async def test_prompt_storage_failure_rolls_back_quote_generation_and_credit_then_same_key_can_retry(
    db, monkeypatch
):
    orchestrator, command, text = await setup_answer(db)
    original = PromptsCommandService.PromptsRepository.create_generation_prompt
    monkeypatch.setattr(
        PromptsCommandService.PromptsRepository,
        "create_generation_prompt",
        AsyncMock(side_effect=RuntimeError("storage down")),
    )
    with pytest.raises(ChatTypes.AnswerStorageError):
        await orchestrator.generate_answer(command)
    text.generate_text.assert_not_awaited()
    async with orchestrator.sessions() as session:
        for model in (
            ProductGeneration,
            GenerationPrompt,
            BillingQuote,
            CreditReservation,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    monkeypatch.setattr(
        PromptsCommandService.PromptsRepository, "create_generation_prompt", original
    )
    answer = await orchestrator.generate_answer(command)
    await check_state(
        orchestrator, command, status="succeeded", balance=10, reserved=0, charge=10
    )
    assert (await read_prompt(orchestrator)).generation_id == answer.generation_id


async def test_simultaneous_first_requests_and_success_replay_store_once(db):
    orchestrator, command, text = await setup_answer(db)
    # Start both before reservation; request-key locking decides one executor.
    first, other = await asyncio.gather(
        orchestrator.generate_answer(command), orchestrator.generate_answer(command)
    )
    assert first.generation_id == other.generation_id
    answer = await orchestrator.generate_answer(command)
    assert answer.status == "succeeded"
    assert text.generate_text.await_count == 1
    stored = await read_prompt(orchestrator)
    assert stored.generation_id == answer.generation_id
    again = await orchestrator.generate_answer(command)
    assert again == answer
    assert (await read_prompt(orchestrator)).created_at == stored.created_at


async def test_failed_provider_prompt_remains_admin_readable_and_credits_released(db):
    orchestrator, command, text = await setup_answer(db)
    admin = await make_admin(db)
    text.generate_text.side_effect = LLMTypes.LLMError(
        "private provider response",
        kind=LLMTypes.LLMErrorKind.TIMEOUT,
        provider=LLMTypes.LLMProvider.OPENAI,
        model="gpt-test",
        retryable=True,
    )
    answer = await orchestrator.generate_answer(command)
    await check_state(
        orchestrator, command, status="failed", balance=20, reserved=0, charge=0
    )
    async with orchestrator.sessions() as session:
        info = await PromptsQueryService.get_generation_prompt(
            session, ChatTypes.GetGenerationPromptCommand(admin, answer.generation_id)
        )
        assert info.generation.status == "failed" and info.prompt is not None
        assert (
            info.prompt.request_json
            == text.generate_text.await_args.args[0].request_json
        )
    assert await orchestrator.generate_answer(command) == answer
    assert text.generate_text.await_count == 1


@pytest.mark.parametrize("phase", ["reserved", "calling", "result_ready"])
async def test_lease_recovery_never_rebuilds_or_repeats_prompt(db, monkeypatch, phase):
    orchestrator, command, text = await setup_answer(db)
    if phase == "result_ready":
        monkeypatch.setattr(
            Answers,
            "finish_generation_and_schedule_memory",
            AsyncMock(side_effect=RuntimeError("storage down")),
        )
    else:
        # Reservation and original prompt are durable; no actual external call happened.
        monkeypatch.setattr(
            orchestrator, "_stage", AsyncMock(side_effect=RuntimeError("stage down"))
        )
    with pytest.raises(ChatTypes.AnswerStorageError):
        await orchestrator.generate_answer(command)
    stored = await read_prompt(orchestrator)
    async with db.begin():
        run = await db.get(ProductGeneration, stored.generation_id)
        metadata = dict(run.answer_metadata)
        if phase != "result_ready":
            metadata["phase"] = phase
        await db.execute(
            update(ProductGeneration).values(
                answer_metadata=metadata,
                answer_lease_until=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    monkeypatch.undo()
    assert await orchestrator.recover_answers() == 1
    recovered = await orchestrator.generate_answer(command)
    assert recovered.status == ("succeeded" if phase == "result_ready" else "failed")
    if phase != "result_ready":
        assert recovered.uncertain is (phase == "calling")
        assert recovered.error_code == (
            "interrupted_uncertain" if phase == "calling" else "interrupted_before_call"
        )
    after = await read_prompt(orchestrator)
    assert (after.request_json, after.digest, after.created_at) == (
        stored.request_json,
        stored.digest,
        stored.created_at,
    )
    assert text.generate_text.await_count == (1 if phase == "result_ready" else 0)
    assert await orchestrator.recover_answers() == 0


async def test_prompt_cannot_be_overwritten_or_duplicated_and_history_edit_does_not_change_it(
    db,
):
    orchestrator, command, _ = await setup_answer(db)
    answer = await orchestrator.generate_answer(command)
    stored = await read_prompt(orchestrator)
    async with orchestrator.sessions() as session:
        run = await session.get(ProductGeneration, answer.generation_id)
        token = run.answer_metadata["execution_token"]
    save = ChatTypes.SaveGenerationPromptCommand(
        generation_id=answer.generation_id,
        user_id=command.user_id,
        execution_token=token,
        request_json=stored.request_json,
        provider=stored.provider,
        max_output_tokens=stored.max_output_tokens,
    )
    async with orchestrator.sessions() as session:
        await PromptsCommandService.save_generation_prompt(session, save)
        with pytest.raises(ChatTypes.MessageConflictError):
            await PromptsCommandService.save_generation_prompt(
                session, replace(save, request_json=stored.request_json + " ")
            )
    async with db.begin():
        db.add(
            GenerationPrompt(
                generation_id=answer.generation_id,
                request_json=stored.request_json,
                digest=stored.digest,
                format_version=1,
                provider=stored.provider,
                max_output_tokens=stored.max_output_tokens,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
    await ChatService.rewind_messages(
        db,
        ChatTypes.RewindMessagesCommand(
            conversation_id=command.conversation_id,
            user_id=command.user_id,
            message_id=command.input_message_id,
        ),
    )
    after = await read_prompt(orchestrator)
    assert (after.request_json, after.digest, after.created_at) == (
        stored.request_json,
        stored.digest,
        stored.created_at,
    )


async def test_real_api_filters_pagination_legacy_not_found_and_active_admin_only(db):
    orchestrator, command, _ = await setup_answer(db)
    answer = await orchestrator.generate_answer(command)
    admin = await make_admin(db)
    legacy_id = uuid4()
    async with db.begin():
        original = await db.get(ProductGeneration, answer.generation_id)
        # Existing generations without a prompt are not backfilled.
        db.add(
            ProductGeneration(
                id=legacy_id,
                user_id=original.user_id,
                conversation_id=original.conversation_id,
                product_id=original.product_id,
                product_snapshot_id=original.product_snapshot_id,
                model_id=original.model_id,
                model_name=original.model_name,
                reasoning_effort=original.reasoning_effort,
                request_key="legacy-generation",
                input_digest="legacy",
                status="failed",
            )
        )
    app = create_app()

    async def session_dependency():
        async with orchestrator.sessions() as session:
            yield session

    async def owner_dependency():
        return admin

    app.dependency_overrides[get_product_session] = session_dependency
    app.dependency_overrides[get_current_owner_id] = owner_dependency
    today = (
        datetime.now(UTC)
        .astimezone(__import__("zoneinfo").ZoneInfo("Asia/Seoul"))
        .date()
        .isoformat()
    )
    params = {
        "date_from": today,
        "date_to": today,
        "page_size": 1,
        "conversation_id": str(command.conversation_id),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = (
            await client.get("/admin/reporting/generation-prompts", params=params)
        ).json()
        second = (
            await client.get(
                "/admin/reporting/generation-prompts", params={**params, "page": 2}
            )
        ).json()
        assert first["total"] == second["total"] == 2
        assert first["items"][0]["generation_id"] != second["items"][0]["generation_id"]
        filtered = (
            await client.get(
                "/admin/reporting/generation-prompts",
                params={**params, "status": "failed"},
            )
        ).json()
        assert filtered["total"] == 1 and not filtered["items"][0]["prompt_recorded"]
        assert (
            await client.get(
                "/admin/reporting/generation-prompts",
                params={**params, "conversation_id": str(uuid4())},
            )
        ).json()["total"] == 0
        assert (
            await client.get(
                "/admin/reporting/generation-prompts",
                params={**params, "date_from": "2000-01-01", "date_to": "2000-01-02"},
            )
        ).json()["total"] == 0
        detail = await client.get(
            f"/admin/reporting/generation-prompts/{answer.generation_id}"
        )
        assert (
            detail.json()["prompt"]["request_json"]
            == (await read_prompt(orchestrator)).request_json
        )
        old = await client.get(f"/admin/reporting/generation-prompts/{legacy_id}")
        assert old.status_code == 200 and old.json()["prompt"] is None
        assert (
            await client.get(f"/admin/reporting/generation-prompts/{uuid4()}")
        ).status_code == 404
        for role, status in [
            ("user", "active"),
            ("admin", "suspended"),
            ("admin", "banned"),
        ]:
            async with db.begin():
                await db.execute(
                    update(User)
                    .where(User.id == admin)
                    .values(role=role, status=status)
                )
            assert (
                await client.get(
                    f"/admin/reporting/generation-prompts/{answer.generation_id}"
                )
            ).status_code == 403
            assert (
                await client.get("/admin/reporting/generation-prompts", params=params)
            ).status_code == 403


async def test_prompt_fk_does_not_allow_orphans_and_cascades_generation_delete(db):
    orchestrator, command, _ = await setup_answer(db)
    # Stop before LLM so there is no completed usage FK preventing intentional generation deletion.
    orchestrator._stage = AsyncMock(side_effect=RuntimeError("stage down"))
    with pytest.raises(ChatTypes.AnswerStorageError):
        await orchestrator.generate_answer(command)
    stored = await read_prompt(orchestrator)
    async with db.begin():
        await db.execute(
            delete(ProductGeneration).where(
                ProductGeneration.id == stored.generation_id
            )
        )
        assert await db.scalar(select(func.count()).select_from(GenerationPrompt)) == 0
    async with db.begin():
        db.add(
            GenerationPrompt(
                generation_id=uuid4(),
                request_json="{}",
                digest="a" * 64,
                format_version=1,
                provider="openai",
                max_output_tokens=1,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
