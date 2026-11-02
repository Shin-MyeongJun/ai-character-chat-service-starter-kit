"""Offline U18 contracts: safe diagnostics and durable reconciliation boundaries."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import exc as SQLAlchemyErrors
from structlog.testing import capture_logs
from test_generation_completion_contracts import Backend
from test_generation_completion_contracts import backend as backend
from test_generation_prompt_workflow import workflow as workflow

from app.http.dependencies import get_current_owner_id
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.router.answers import get_answer_orchestrator, router
from app.modules.chatting.chat.service.util import answer_diagnostics as Diagnostics
from app.modules.chatting.chat.service.workflow import answers as Answers
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.commerce.billing import types as BillingTypes
from app.modules.llm import types as LLMTypes


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["session", "request", "preparation", "commit"])
@pytest.mark.parametrize("kind", ["storage", "internal"])
async def test_initial_read_failure_is_diagnosed_without_consuming_request(
    workflow: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    kind: str,
) -> None:
    failure = (
        SQLAlchemyErrors.TimeoutError("SECRET pool details")
        if kind == "storage"
        else TypeError("SECRET implementation details")
    )
    orchestrator = workflow.orchestrator
    with monkeypatch.context() as patch:
        if boundary in ("session", "commit"):
            original = (
                orchestrator.sessions
                if boundary == "session"
                else Answers.use_case_transaction
            )

            @asynccontextmanager
            async def failing_scope(*args: object) -> AsyncIterator[object]:
                if boundary == "session":
                    raise failure
                async with original(*args) as value:
                    yield value
                raise failure

            if boundary == "session":
                patch.setattr(orchestrator, "sessions", failing_scope)
            else:
                patch.setattr(Answers, "use_case_transaction", failing_scope)
        else:
            patch.setattr(
                orchestrator,
                "_get_request" if boundary == "request" else "_read_preparation",
                AsyncMock(side_effect=failure),
            )
        expected = Types.AnswerStorageError if kind == "storage" else RuntimeError
        with capture_logs() as logs, pytest.raises(expected) as caught:
            await orchestrator.generate_answer(workflow.command)
    assert caught.value.__cause__ is failure
    assert "SECRET" not in str(caught.value)
    assert len(logs) == 1
    assert logs[0]["phase"] == "preparation_read"
    assert logs[0]["failure_class"] == (
        "storage_unavailable" if kind == "storage" else "internal"
    )
    assert logs[0]["diagnostic_id"] and logs[0]["generation_id"] is None
    assert not logs[0]["storage_uncertain"]
    assert "SECRET" not in json.dumps(logs)
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    Answers.BillingCreditService.reserve_credit.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()
    assert workflow.saved == []
    assert await orchestrator.generate_answer(workflow.command) == workflow.answer
    workflow.text.generate_text.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ValueError("invalid input"),
        LookupError("not owned"),
        Types.MessageConflictError("different request"),
        BillingTypes.BillingPricingError("not configured"),
    ],
)
async def test_initial_read_preserves_expected_domain_errors(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    monkeypatch.setattr(
        workflow.orchestrator, "_read_preparation", AsyncMock(side_effect=failure)
    )
    with capture_logs() as logs, pytest.raises(type(failure)) as caught:
        await workflow.orchestrator.generate_answer(workflow.command)
    assert caught.value is failure
    assert logs == []
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["_get_request", "_read_preparation"])
async def test_initial_read_cancellation_propagates(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    monkeypatch.setattr(
        workflow.orchestrator, method, AsyncMock(side_effect=asyncio.CancelledError())
    )
    with capture_logs() as logs, pytest.raises(asyncio.CancelledError):
        await workflow.orchestrator.generate_answer(workflow.command)
    assert logs == []
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["storage", "internal"])
async def test_initial_read_http_errors_hide_details_and_keep_storage_retry_contract(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    # NoSuchColumnError is also a LookupError: storage classification must win.
    failure = (
        SQLAlchemyErrors.NoSuchColumnError("SECRET column")
        if kind == "storage"
        else TypeError("SECRET implementation")
    )
    monkeypatch.setattr(
        workflow.orchestrator, "_read_preparation", AsyncMock(side_effect=failure)
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = lambda: workflow.command.user_id
    app.dependency_overrides[get_answer_orchestrator] = lambda: workflow.orchestrator
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/conversations/{workflow.command.conversation_id}/answers",
            json={
                "request_key": workflow.command.request_key,
                "input_message_id": str(workflow.command.input_message_id),
                "expected_revision": workflow.command.expected_revision,
                "product_character_id": str(workflow.command.product_character_id),
            },
        )
    assert response.status_code == (503 if kind == "storage" else 500)
    assert "SECRET" not in response.text
    if kind == "storage":
        assert response.json()["detail"] == {
            "code": "storage_pending_recovery",
            "retry_same_key": True,
        }
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TypeError("private"), ValueError("invalid_usage")])
async def test_internal_preparation_failure_does_not_consume_key_or_reserve(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    prepare = Answers.prepare_answer_context
    monkeypatch.setattr(
        Answers, "prepare_answer_context", AsyncMock(side_effect=failure)
    )
    with capture_logs() as logs, pytest.raises(RuntimeError) as caught:
        await workflow.orchestrator.generate_answer(workflow.command)
    assert caught.value.__cause__ is failure
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    Answers.BillingCreditService.reserve_credit.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()
    assert workflow.saved == []
    assert logs[0]["phase"] == "preparing"
    assert logs[0]["failure_class"] == "internal"
    assert logs[0]["diagnostic_id"]
    assert "private" not in json.dumps(logs)
    monkeypatch.setattr(Answers, "prepare_answer_context", prepare)
    assert (
        await workflow.orchestrator.generate_answer(workflow.command) == workflow.answer
    )
    workflow.text.generate_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_preparation_storage_outage_keeps_same_key_available(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    failure = SQLAlchemyErrors.TimeoutError("private pool details")
    monkeypatch.setattr(
        Answers, "prepare_answer_context", AsyncMock(side_effect=failure)
    )
    with capture_logs() as logs, pytest.raises(Types.AnswerStorageError) as caught:
        await workflow.orchestrator.generate_answer(workflow.command)
    assert caught.value.__cause__ is failure
    assert logs[0]["failure_class"] == "storage_unavailable"
    assert not logs[0]["storage_uncertain"]
    Answers.GenerationCommandService.begin_generation.assert_not_awaited()
    Answers.BillingCreditService.reserve_credit.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["budget", "embedding", "timeout"])
async def test_expected_preparation_failure_still_writes_unbilled_receipt(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    failures = {
        "budget": MemoryTypes.ContextBudgetExceededError(
            "private", summary_required=True
        ),
        "embedding": LLMTypes.EmbeddingError(
            "private",
            kind=LLMTypes.EmbeddingErrorKind.RATE_LIMIT,
            provider=LLMTypes.EmbeddingProvider.VOYAGE,
            model="test",
            retryable=True,
        ),
        "timeout": TimeoutError("private"),
    }
    update = AsyncMock()
    monkeypatch.setattr(
        Answers, "prepare_answer_context", AsyncMock(side_effect=failures[kind])
    )
    monkeypatch.setattr(Answers.AnswersCommandService, "update_answer", update)
    with capture_logs() as logs:
        await workflow.orchestrator.generate_answer(workflow.command)
    preparation_log = next(
        item for item in logs if item["event"] == "answer_preparation_failed"
    )
    reservation_log = next(
        item for item in logs if item["event"] == "answer_reservation_committed"
    )
    assert preparation_log["diagnostic_id"] == reservation_log["diagnostic_id"]
    assert reservation_log["generation_id"] == str(workflow.answer.generation_id)
    metadata = update.await_args.args[1].metadata
    assert metadata["phase"] == "result_ready"
    assert metadata["unbilled_reason"] == "preparation_failed"
    assert metadata["retryable"]
    assert (
        metadata["error_code"]
        == {
            "budget": "summary_required",
            "embedding": "memory_rate_limit",
            "timeout": "timeout",
        }[kind]
    )
    Answers.BillingCreditService.reserve_credit.assert_not_awaited()
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [KeyError("private"), SQLAlchemyErrors.TimeoutError("private")]
)
async def test_finalize_failure_keeps_primary_cause_when_reconciliation_also_fails(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    orchestrator = workflow.orchestrator
    finalize = AsyncMock(side_effect=failure)
    monkeypatch.setattr(orchestrator, "_finalize", finalize)
    monkeypatch.setattr(
        Answers.GenerationQueryService,
        "get_generation_state",
        AsyncMock(side_effect=RuntimeError("private read")),
    )
    # Use the actual completion method, not the prompt workflow fixture's stub.
    with capture_logs() as logs, pytest.raises(Types.AnswerStorageError) as caught:
        await Answers.AnswerOrchestrator._complete_staged(
            orchestrator, uuid4(), uuid4()
        )
    assert caught.value.__cause__ is failure
    assert [item["event"] for item in logs] == [
        "answer_finalize_failed",
        "answer_reconciliation_failed",
    ]
    assert logs[0]["failure_class"] == (
        "internal" if isinstance(failure, KeyError) else "storage_unavailable"
    )
    assert all(item["storage_uncertain"] for item in logs)
    assert "private" not in json.dumps(logs)
    workflow.text.generate_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["completion", "resume", "background"])
async def test_lost_final_commit_ack_returns_durable_terminal_without_repeating_effects(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    item = backend
    original = item.orchestrator._finalize

    async def lost_ack(*args: object, **kwargs: object) -> Types.AnswerInfo:
        await original(item.generation_id, item.owner_id, recover=entry != "completion")
        raise RuntimeError("private commit acknowledgement")

    monkeypatch.setattr(item.orchestrator, "_finalize", lost_ack)
    if entry == "completion":
        answer = await item.orchestrator._complete_staged(
            item.generation_id, item.owner_id
        )
    elif entry == "resume":
        async with item.sessions() as session:
            run = await Answers.GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=item.generation_id, user_id=item.owner_id
                ),
            )
        answer = await item.orchestrator._resume(run)
    else:
        item.change(answer_lease_until=datetime.now(UTC) - timedelta(seconds=1))
        assert await item.orchestrator.recover_answers() == 1
        async with item.sessions() as session:
            run = await Answers.GenerationQueryService.get_generation_state(
                session,
                Types.GetGenerationStateCommand(
                    generation_id=item.generation_id, user_id=item.owner_id
                ),
            )
        answer = Answers._answer_info(run)
    assert answer.status == "succeeded" and answer.content == "Output"
    assert (
        item.effect_count("usage")
        == item.effect_count("credit")
        == item.effect_count("memory")
        == 1
    )
    assert item.state().answer_recovery_attempts == (0 if entry == "completion" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["scan", "finalize"])
async def test_recovery_cancellation_propagates_without_failure_translation(
    workflow: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    orchestrator = workflow.orchestrator
    monkeypatch.setattr(
        orchestrator,
        "_complete_staged",
        Answers.AnswerOrchestrator._complete_staged.__get__(orchestrator),
    )
    scan = AsyncMock(return_value=[SimpleNamespace(id=uuid4(), user_id=uuid4())])
    monkeypatch.setattr(Answers.AnswersCommandService, "list_expired_answers", scan)
    monkeypatch.setattr(
        Answers.AnswerRecoveryCommandService,
        "claim_answer_recovery",
        AsyncMock(
            return_value=Types.AnswerRecoveryClaimInfo(
                SimpleNamespace(status="pending"), 1
            )
        ),
    )
    if phase == "scan":
        scan.side_effect = asyncio.CancelledError()
    else:
        monkeypatch.setattr(
            orchestrator, "_finalize", AsyncMock(side_effect=asyncio.CancelledError())
        )
    with capture_logs() as logs, pytest.raises(asyncio.CancelledError):
        await orchestrator.recover_answers()
    assert logs == []


@pytest.mark.parametrize(
    "error,expected",
    [
        (
            SQLAlchemyErrors.IntegrityError(
                "SECRET SQL", {"password": "SECRET"}, RuntimeError("SECRET")
            ),
            "storage_constraint",
        ),
        (
            SQLAlchemyErrors.OperationalError("SECRET SQL", {}, RuntimeError("SECRET")),
            "storage_error",
        ),
        (
            SQLAlchemyErrors.OperationalError(
                "SECRET SQL", {}, RuntimeError("SECRET"), connection_invalidated=True
            ),
            "storage_unavailable",
        ),
        (Types.AnswerStateError("SECRET"), "invariant"),
        (TypeError("SECRET"), "internal"),
    ],
)
def test_diagnostics_classify_by_type_without_messages(
    error: Exception, expected: str
) -> None:
    details = Diagnostics.error_details(error)
    assert details["failure_class"] == expected
    assert "SECRET" not in json.dumps(details)


def test_sanitized_stack_has_locations_without_source_locals_or_absolute_paths() -> (
    None
):
    secret = "SECRET"
    try:
        Answers._validate_result(
            LLMTypes.LLMResultInfo(
                "", LLMTypes.LLMProvider.MOCK, secret, LLMTypes.TokenUsageInfo()
            )
        )
    except ValueError as error:
        details = Diagnostics.error_details(error)
    rendered = json.dumps(details)
    assert "SECRET" not in rendered
    assert str(Diagnostics.APPLICATION_ROOT) not in rendered
    assert "_validate_result" in rendered and "answers.py" in rendered
    assert all(
        set(frame) == {"file", "function", "line"} for frame in details["stack_frames"]
    )


def test_cyclic_exception_causes_are_bounded_and_never_stringified() -> None:
    class PrivateError(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("Do not stringify private errors")

    error = Types.AnswerStorageError("SECRET")
    cause = PrivateError("SECRET")
    error.__cause__ = cause
    cause.__cause__ = error
    details = Diagnostics.error_details(error)
    assert details["exception_chain"] == ["AnswerStorageError", "PrivateError"]
    assert "SECRET" not in json.dumps(details)


def test_plain_exception_message_cannot_impersonate_result_validation() -> None:
    assert Answers._classify_error(ValueError("invalid_usage"), "calling") == (
        "internal_error",
        False,
        True,
    )
