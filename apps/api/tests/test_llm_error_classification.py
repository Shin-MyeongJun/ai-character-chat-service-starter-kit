"""Transient SDK failures stay retryable; local and parsing failures do not."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx
import openai
import pytest

from app.modules.llm.adapters import AnthropicAdapter, OpenAIAdapter
from app.modules.llm.types import LLMError, LLMErrorKind


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("failure_kind", ["type", "json", "runtime", "sdk", "schema"])
async def test_nontransient_call_failures_are_not_retryable(
    provider: str, failure_kind: str
) -> None:
    sdk = openai if provider == "openai" else anthropic
    request = httpx.Request("POST", "https://example.test")
    failures = {
        "type": TypeError("SDK programming failure"),
        "json": json.JSONDecodeError("invalid JSON", "{", 1),
        "runtime": RuntimeError("unexpected failure"),
        "sdk": sdk.APIError("unclassified SDK failure", request, body=None),
        "schema": sdk.APIResponseValidationError(
            response=httpx.Response(200, request=request), body={}
        ),
    }
    failure = failures[failure_kind]
    create = AsyncMock(side_effect=failure)
    resource = SimpleNamespace(create=create)
    client = SimpleNamespace(responses=resource, messages=resource)
    adapter = (
        OpenAIAdapter(client=client)
        if provider == "openai"
        else AnthropicAdapter(client=client)
    )
    model = "gpt-test" if provider == "openai" else "claude-test"
    with pytest.raises(LLMError) as caught:
        await adapter.generate("request", model=model)
    assert caught.value.kind is LLMErrorKind.PROVIDER
    assert not caught.value.retryable
    assert caught.value.model == model
    assert caught.value.provider.value == provider
    assert caught.value.__cause__ is failure
    create.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_sdk_call_cancellation_is_not_wrapped(provider: str) -> None:
    failure = asyncio.CancelledError()
    create = AsyncMock(side_effect=failure)
    resource = SimpleNamespace(create=create)
    client = SimpleNamespace(responses=resource, messages=resource)
    adapter = (
        OpenAIAdapter(client=client)
        if provider == "openai"
        else AnthropicAdapter(client=client)
    )
    with pytest.raises(asyncio.CancelledError) as caught:
        await adapter.generate(
            "request", model="gpt-test" if provider == "openai" else "claude-test"
        )
    assert caught.value is failure
    create.assert_awaited_once()
