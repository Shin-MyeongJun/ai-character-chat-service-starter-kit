"""SDK boundary compatibility: dict responses, raw usage and optional close."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.llm.adapters import AnthropicAdapter, OpenAIAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("usage_kind", ["missing", "zero", "malformed_bool"])
async def test_dict_responses_preserve_provider_usage_defaults_and_raw_values(
    provider: str, usage_kind: str
) -> None:
    response: dict[str, object] = {
        "output_text": "Answer",
        "content": [
            {"type": "thinking", "thinking": "private"},
            {"type": "text", "text": "Answer"},
            {"type": "text", "text": None},
        ],
        "model": None,
    }
    if usage_kind == "zero":
        response["usage"] = {"input_tokens": 0, "output_tokens": 0}
    elif usage_kind == "malformed_bool":
        # Type projections must not invent validation or silently turn this into 1.
        response["usage"] = {"input_tokens": True}
    create = AsyncMock(return_value=response)
    resource = SimpleNamespace(create=create)
    client = SimpleNamespace(responses=resource, messages=resource)
    adapter = (
        OpenAIAdapter(client=client)
        if provider == "openai"
        else AnthropicAdapter(client=client)
    )
    model = "gpt-test" if provider == "openai" else "claude-test"
    result = await adapter.generate("legacy request", model=model)
    assert result.content == "Answer" and result.model == model
    assert result.response_id is None and result.request_id is None
    assert result.usage.cache_creation_input_tokens is None
    assert result.usage.reasoning_tokens is None
    if usage_kind == "missing":
        assert result.usage.input_tokens is None
        assert result.usage.output_tokens is None
        assert result.usage.total_tokens is None
    elif usage_kind == "zero":
        assert type(result.usage.input_tokens) is int
        assert result.usage.input_tokens == 0 and result.usage.output_tokens == 0
        # Anthropic sums known counts; OpenAI preserves the explicit total field.
        assert result.usage.total_tokens == (0 if provider == "anthropic" else None)
    else:
        assert result.usage.input_tokens is True
        assert result.usage.total_tokens == (1 if provider == "anthropic" else None)
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_malformed_anthropic_usage_still_fails_after_call_without_retry() -> None:
    create = AsyncMock(
        return_value={
            "content": [{"type": "text", "text": "Answer"}],
            "usage": {"input_tokens": "not-a-count", "output_tokens": 1},
        }
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with pytest.raises(TypeError):
        await AnthropicAdapter(client=client).generate(
            "legacy request", model="claude-test"
        )
    create.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
@pytest.mark.parametrize("close_kind", ["missing", "failure"])
async def test_injected_client_optional_close_and_original_close_failure_are_preserved(
    provider: str, close_kind: str
) -> None:
    create = AsyncMock()
    resource = SimpleNamespace(create=create)
    client = SimpleNamespace(responses=resource, messages=resource)
    failure = RuntimeError("close failed")
    close = AsyncMock(side_effect=failure)
    if close_kind == "failure":
        client.close = close
    adapter = (
        OpenAIAdapter(client=client)
        if provider == "openai"
        else AnthropicAdapter(client=client)
    )
    if close_kind == "failure":
        with pytest.raises(RuntimeError) as caught:
            await adapter.aclose()
        assert caught.value is failure
        close.assert_awaited_once()
    else:
        await adapter.aclose()
        close.assert_not_awaited()
    create.assert_not_awaited()
