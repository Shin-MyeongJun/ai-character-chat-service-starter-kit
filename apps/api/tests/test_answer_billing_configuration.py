"""Server pricing setup and HTTP errors: no implicit operational policy."""

import json
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from answer_billing_support import answer_pricing
from app.http.dependencies import get_current_owner_id
from app.modules.chatting.chat.router.answers import get_answer_orchestrator, router
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service.configuration import (
    load_billing_pricing_configuration,
)
from fastapi import FastAPI


def test_pricing_file_roundtrip_and_missing_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("BILLING_PRICING_CONFIG_PATH", raising=False)
    assert load_billing_pricing_configuration() is None
    configuration = answer_pricing(uuid4())
    path = tmp_path / "prices.json"
    data = {"price_book": asdict(configuration.price_book), "quote_ttl_seconds": 60}
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    monkeypatch.setenv("BILLING_PRICING_CONFIG_PATH", str(path))
    assert load_billing_pricing_configuration() == configuration
    for value in (True, 1.2, "NaN", "-1", ""):
        data["price_book"]["credits_per_currency_unit"] = value
        path.write_text(json.dumps(data, default=str), encoding="utf-8")
        with pytest.raises(BillingTypes.BillingPricingError):
            load_billing_pricing_configuration()
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(BillingTypes.BillingPricingError):
        load_billing_pricing_configuration()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status,code",
    [
        (BillingTypes.InsufficientCreditError, 402, "insufficient_credit"),
        (BillingTypes.CreditAccountNotFoundError, 409, "credit_account_unavailable"),
        (BillingTypes.BillingPricingError, 503, "billing_not_configured"),
        (BillingTypes.BillingQuoteExpiredError, 409, "billing_conflict"),
        (BillingTypes.BillingQuoteConflictError, 409, "billing_conflict"),
        (BillingTypes.CreditReservationConflictError, 409, "billing_conflict"),
    ],
)
async def test_billing_errors_use_existing_answer_http_boundary(error, status, code):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = uuid4
    app.dependency_overrides[get_answer_orchestrator] = lambda: SimpleNamespace(
        generate_answer=AsyncMock(side_effect=error("private policy details"))
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/conversations/{uuid4()}/answers",
            json={
                "request_key": "legacy-string-key",
                "input_message_id": str(uuid4()),
                "expected_revision": 1,
                "product_character_id": str(uuid4()),
            },
        )
    assert response.status_code == status
    assert response.json()["detail"] == {"code": code}
