"""Owner authorization, immutable credit query mapping and private-field exclusion."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.http import dependencies
from app.http.account_credits import router
from app.modules.commerce.credit import types as CreditTypes
from app.modules.commerce.credit.service import query as CreditQueryService
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def make_client(owner, session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner
    app.dependency_overrides[dependencies.get_product_session] = lambda: session
    return TestClient(app)


def test_history_maps_owner_credit_currency_and_cursor_without_private_fields(
    monkeypatch,
):
    owner, transaction_id = uuid4(), uuid4()
    stamp = datetime(2026, 10, 19, 6, 20, tzinfo=UTC)
    item = CreditTypes.CreditTransactionInfo(
        id=transaction_id,
        user_id=owner,
        currency_code="CREDIT",
        namespace="private",
        request_key=uuid4(),
        operation="consume",
        amount=-120,
        reason="internal",
        reference_id=uuid4(),
        idempotency_key="secret",
        created_at=stamp,
        free_amount=-20,
        paid_amount=-100,
    )
    query = AsyncMock(
        return_value=CreditTypes.CreditTransactionPageInfo(
            items=(item,),
            next_cursor=CreditTypes.CreditCursor(created_at=stamp, id=transaction_id),
        )
    )
    monkeypatch.setattr(CreditQueryService, "list_credit_transactions", query)
    session = object()
    with make_client(owner, session) as client:
        response = client.get(
            "/account/credits/transactions",
            params={
                "start": "2026-10-01T00:00:00Z",
                "cursor_created_at": stamp.isoformat(),
                "cursor_id": str(transaction_id),
                "limit": 1,
            },
        )
    assert response.status_code == 200
    value = response.json()
    assert value["items"][0] == {
        "id": str(transaction_id),
        "operation": "consume",
        "amount": -120,
        "free_amount": -20,
        "paid_amount": -100,
        "created_at": "2026-10-19T06:20:00Z",
    }
    assert value["next_cursor_id"] == str(transaction_id)
    command = query.await_args.args[1]
    assert query.await_args.args[0] is session
    assert command.user_id == owner and command.currency_code == "CREDIT"
    assert command.limit == 1 and command.cursor.id == transaction_id
    assert command.start == datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "params",
    [
        {"user_id": str(uuid4())},
        {"currency_code": "OTHER"},
        {"limit": 101},
        {"cursor_id": str(uuid4())},
        {"cursor_created_at": "2026-10-19T06:20:00Z"},
        {"start": "2026-10-19T00:00:00"},
        {"start": "2026-10-20T00:00:00Z", "end": "2026-10-19T00:00:00Z"},
    ],
)
def test_invalid_history_queries_do_not_reach_service(monkeypatch, params):
    query = AsyncMock()
    monkeypatch.setattr(CreditQueryService, "list_credit_transactions", query)
    with make_client(uuid4(), object()) as client:
        assert (
            client.get("/account/credits/transactions", params=params).status_code
            == 422
        )
    query.assert_not_awaited()


def test_auth_denial_prevents_history_query(monkeypatch):
    query = AsyncMock()
    monkeypatch.setattr(CreditQueryService, "list_credit_transactions", query)
    app = FastAPI()
    app.include_router(router)

    def deny():
        raise HTTPException(401, "Authentication required")

    app.dependency_overrides[dependencies.get_current_owner_id] = deny
    app.dependency_overrides[dependencies.get_product_session] = lambda: object()
    with TestClient(app) as client:
        assert client.get("/account/credits/transactions").status_code == 401
    query.assert_not_awaited()


def test_storage_failure_is_not_an_empty_success(monkeypatch):
    monkeypatch.setattr(
        CreditQueryService,
        "list_credit_transactions",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )
    with (
        make_client(uuid4(), object()) as client,
        pytest.raises(RuntimeError, match="storage unavailable"),
    ):
        client.get("/account/credits/transactions")
