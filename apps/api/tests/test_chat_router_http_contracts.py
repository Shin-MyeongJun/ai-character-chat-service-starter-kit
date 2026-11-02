"""Exercise chat HTTP contracts with service doubles, without a database."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.dependencies import get_current_owner_id, get_product_session
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.dependencies import get_answer_orchestrator
from app.modules.chatting.chat.router import messages as MessagesRouter
from app.modules.chatting.chat.router import router
from app.modules.commerce.billing import types as BillingTypes

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def owner() -> UUID:
    return uuid4()


@pytest_asyncio.fixture
async def client(app: FastAPI, owner: UUID) -> AsyncIterator[AsyncClient]:
    # No SQL is issued: router tests replace each service below.
    async with AsyncSession() as session:
        app.dependency_overrides[get_product_session] = lambda: session
        app.dependency_overrides[get_current_owner_id] = lambda: owner
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client


async def _request_message(
    client: AsyncClient, method: str, conversation_id: UUID
) -> Response:
    path = f"/conversations/{conversation_id}/messages"
    if method == "POST":
        return await client.post(
            path, json={"request_key": "message-1", "content": "Hello"}
        )
    if method == "PUT":
        return await client.put(
            f"{path}/{uuid4()}", json={"content": "Hello", "expected_revision": 1}
        )
    if method == "DELETE":
        return await client.delete(f"{path}/{uuid4()}")
    return await client.get(path)


def _mock_message_services(monkeypatch: pytest.MonkeyPatch, service: AsyncMock) -> None:
    monkeypatch.setattr(
        MessagesRouter.MessagesCommandService, "create_message", service
    )
    monkeypatch.setattr(
        MessagesRouter.MessagesCommandService, "replace_message", service
    )
    monkeypatch.setattr(
        MessagesRouter.MessagesCommandService, "rewind_messages", service
    )
    monkeypatch.setattr(MessagesRouter.MessagesQueryService, "list_messages", service)


@pytest.mark.parametrize("method", ["POST", "GET", "PUT", "DELETE"])
async def test_message_response_and_authenticated_command(
    client: AsyncClient, owner: UUID, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    conversation_id = uuid4()
    message = Types.MessageInfo(
        id=uuid4(),
        conversation_id=conversation_id,
        sender_type="user",
        content="Hello",
        position=7,
        revision=1,
        created_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
        character_id=None,
        product_character_id=None,
        product_snapshot_id=None,
        generation_id=None,
        generated_by_ai=False,
        model_id=None,
    )
    message_body = {
        "id": str(message.id),
        "conversation_id": str(conversation_id),
        "sender_type": "user",
        "content": "Hello",
        "position": 7,
        "revision": 1,
        "created_at": "2026-10-28T00:00:00Z",
        "character_id": None,
        "product_character_id": None,
        "product_snapshot_id": None,
        "generation_id": None,
        "generated_by_ai": False,
        "model_id": None,
    }
    service = AsyncMock(return_value=message)
    if method == "GET":
        service.return_value = Types.MessagePageInfo(
            items=(message,),
            next_cursor=Types.MessageCursor(conversation_id, 7),
            history_revision=3,
            sync_cursor=Types.MessageCursor(conversation_id, 7),
        )
    elif method == "DELETE":
        service.return_value = Types.RewindMessagesInfo(deleted_count=2)
    _mock_message_services(monkeypatch, service)

    response = await _request_message(client, method, conversation_id)

    assert response.status_code == (201 if method == "POST" else 200)
    if method == "GET":
        assert response.json() == {
            "items": [message_body],
            "next_cursor": f"v1:{conversation_id}:7",
            "history_revision": 3,
            "sync_cursor": f"v1:{conversation_id}:7",
        }
    elif method == "DELETE":
        assert response.json() == {"deleted_count": 2}
    else:
        assert response.json() == message_body
    service.assert_awaited_once()
    assert service.await_args is not None
    command = service.await_args.args[1]
    assert command.user_id == owner
    assert command.conversation_id == conversation_id


@pytest.mark.parametrize("method", ["POST", "GET", "PUT", "DELETE"])
@pytest.mark.parametrize(
    "error,status",
    [
        (Types.MessageConflictError("pending generation"), 409),
        (Types.MessagePermissionError("character message"), 403),
        (LookupError("message not found"), 404),
        (ValueError("invalid message"), 422),
    ],
)
async def test_message_error_status_and_body(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    error: Exception,
    status: int,
) -> None:
    service = AsyncMock(side_effect=error)
    _mock_message_services(monkeypatch, service)

    response = await _request_message(client, method, uuid4())

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}
    service.assert_awaited_once()


async def _request_answer(client: AsyncClient) -> Response:
    return await client.post(
        f"/conversations/{uuid4()}/answers",
        json={
            "request_key": "answer-1",
            "input_message_id": str(uuid4()),
            "expected_revision": 1,
            "product_character_id": str(uuid4()),
        },
    )


@pytest.mark.parametrize(
    "status,code,http_status",
    [
        ("succeeded", None, 200),
        ("pending", None, 202),
        ("failed", "summary_required", 409),
        ("stale", "stale", 409),
        ("cancelled", "cancelled", 409),
        ("failed", "interrupted_before_call", 409),
        ("failed", "fixed_context_exceeded", 422),
        ("failed", "unsupported_model", 422),
        ("failed", "llm_rate_limit", 429),
        ("failed", "llm_timeout", 504),
        ("failed", "timeout", 504),
        ("failed", "llm_authentication", 502),
        ("failed", "future_error", 502),
        ("failed", None, 502),
    ],
)
async def test_answer_status_body_and_retry_after(
    app: FastAPI,
    client: AsyncClient,
    status: str,
    code: str | None,
    http_status: int,
) -> None:
    info = Types.AnswerInfo(
        generation_id=uuid4(),
        status=status,
        content="Answer" if status == "succeeded" else None,
        model="test-model",
        error_code=code,
        retryable=True,
        uncertain=True,
        price_credit=17,
    )
    service = AsyncMock(return_value=info)
    app.dependency_overrides[get_answer_orchestrator] = lambda: SimpleNamespace(
        generate_answer=service
    )

    response = await _request_answer(client)

    assert response.status_code == http_status
    assert response.json() == {
        "generation_id": str(info.generation_id),
        "status": status,
        "content": info.content,
        "model": "test-model",
        "error_code": code,
        "retryable": True,
        "uncertain": True,
        "price_credit": 17,
    }
    assert response.headers.get("retry-after") == ("3" if status == "pending" else None)


@pytest.mark.parametrize(
    "error,status,detail",
    [
        (
            BillingTypes.InsufficientCreditError("private"),
            402,
            {"code": "insufficient_credit"},
        ),
        (
            BillingTypes.CreditAccountNotFoundError("private"),
            409,
            {"code": "credit_account_unavailable"},
        ),
        (
            BillingTypes.BillingPricingError("private"),
            503,
            {"code": "billing_not_configured"},
        ),
        (
            BillingTypes.BillingQuoteConflictError("private"),
            409,
            {"code": "billing_conflict"},
        ),
        (
            BillingTypes.BillingQuoteExpiredError("private"),
            409,
            {"code": "billing_conflict"},
        ),
        (
            BillingTypes.CreditReservationConflictError("private"),
            409,
            {"code": "billing_conflict"},
        ),
        (LookupError("private"), 404, "Conversation or input not found."),
        (Types.MessageConflictError("revision conflict"), 409, "revision conflict"),
        (ValueError("invalid answer"), 422, "invalid answer"),
        (
            Types.AnswerStorageError("private"),
            503,
            {"code": "storage_pending_recovery", "retry_same_key": True},
        ),
    ],
)
async def test_answer_exception_status_and_body(
    app: FastAPI,
    client: AsyncClient,
    error: Exception,
    status: int,
    detail: str | dict[str, str | bool],
) -> None:
    service = AsyncMock(side_effect=error)
    app.dependency_overrides[get_answer_orchestrator] = lambda: SimpleNamespace(
        generate_answer=service
    )

    response = await _request_answer(client)

    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "retry-after" not in response.headers
    service.assert_awaited_once()
