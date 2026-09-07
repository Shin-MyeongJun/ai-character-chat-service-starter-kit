from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from anthropic.types import Message
from openai.types.responses import Response

from app.modules.llm import (
    LLMError,
    LLMErrorKind,
    LLMProvider,
    LLMService,
    ReasoningEffort,
    UnsupportedModelError,
    UnsupportedReasoningEffortError,
)
from app.modules.llm.adapters import AnthropicAdapter, OpenAIAdapter

pytestmark = pytest.mark.asyncio


def openai_client(response):
    return SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response)),
        close=AsyncMock(),
    )


def anthropic_client(response):
    return SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=response)),
        close=AsyncMock(),
    )


async def test_service_routes_openai_and_preserves_usage():
    response = SimpleNamespace(
        output_text='{"answer":"ok"}',
        output=[],
        model="gpt-test-actual",
        id="resp_123",
        _request_id="req_123",
        status="completed",
        incomplete_details=None,
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=40,
            total_tokens=140,
            input_tokens_details=SimpleNamespace(
                cached_tokens=25,
                cache_write_tokens=5,
            ),
            output_tokens_details=SimpleNamespace(reasoning_tokens=12),
        ),
    )
    client = openai_client(response)
    adapter = OpenAIAdapter(
        client=client,
        model_reasoning_efforts={"gpt-test": {"low", "high"}},
    )
    service = LLMService([adapter])

    result = await service.generate(
        '{"prompt":"hello"}',
        model="gpt-test",
        reasoning_effort="high",
        max_output_tokens=500,
    )

    assert result.content == '{"answer":"ok"}'
    assert result.provider is LLMProvider.OPENAI
    assert result.model == "gpt-test-actual"
    assert result.response_id == "resp_123"
    assert result.request_id == "req_123"
    assert result.usage.input_tokens == 100
    assert result.usage.cached_input_tokens == 25
    assert result.usage.cache_creation_input_tokens == 5
    assert result.usage.reasoning_tokens == 12
    assert client.responses.create.await_args.kwargs == {
        "model": "gpt-test",
        "input": '{"prompt":"hello"}',
        "max_output_tokens": 500,
        "store": False,
        "reasoning": {"effort": "high"},
    }


async def test_anthropic_extracts_only_text_and_detailed_usage():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="private"),
            SimpleNamespace(type="text", text="first"),
            SimpleNamespace(type="text", text=" second"),
        ],
        model="claude-test-actual",
        id="msg_123",
        _request_id="req_456",
        stop_reason="end_turn",
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=70,
            output_tokens=30,
            cache_creation_input_tokens=20,
            cache_read_input_tokens=10,
            cache_creation=SimpleNamespace(
                ephemeral_5m_input_tokens=12,
                ephemeral_1h_input_tokens=8,
            ),
            output_tokens_details=SimpleNamespace(thinking_tokens=8),
        ),
    )
    client = anthropic_client(response)
    adapter = AnthropicAdapter(
        client=client,
        model_reasoning_efforts={"claude-test": {ReasoningEffort.MEDIUM}},
    )
    service = LLMService([adapter])

    result = await service.generate(
        '{"prompt":"hello"}',
        model="claude-test",
        reasoning_effort=ReasoningEffort.MEDIUM,
    )

    assert result.content == "first second"
    assert result.provider is LLMProvider.ANTHROPIC
    assert result.usage.total_tokens == 130
    assert result.usage.cache_creation_input_tokens == 20
    assert result.usage.cache_creation_5m_input_tokens == 12
    assert result.usage.cache_creation_1h_input_tokens == 8
    assert result.usage.cache_read_input_tokens == 10
    assert result.usage.reasoning_tokens == 8
    assert client.messages.create.await_args.kwargs == {
        "model": "claude-test",
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": '{"prompt":"hello"}'}],
        "output_config": {"effort": "medium"},
    }


async def test_model_capabilities_are_validated_before_calling_provider():
    client = openai_client(SimpleNamespace())
    adapter = OpenAIAdapter(
        client=client,
        model_reasoning_efforts={"gpt-test": {"low"}},
    )
    service = LLMService([adapter])

    with pytest.raises(UnsupportedReasoningEffortError):
        await service.generate("{}", model="gpt-test", reasoning_effort="high")
    with pytest.raises(UnsupportedModelError):
        await service.generate("{}", model="gpt-unknown")
    with pytest.raises(UnsupportedReasoningEffortError, match="Unknown"):
        await service.generate("{}", model="gpt-test", reasoning_effort="extreme")
    with pytest.raises(ValueError, match="max_output_tokens"):
        await service.generate("{}", model="gpt-test", max_output_tokens=0)
    client.responses.create.assert_not_awaited()


async def test_incomplete_and_refusal_responses_keep_usage_and_reason():
    response = SimpleNamespace(
        output_text="",
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="refusal", refusal="declined")]
            )
        ],
        model="gpt-test",
        id="resp_refused",
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        usage=SimpleNamespace(
            input_tokens=5,
            output_tokens=2,
            total_tokens=7,
            input_tokens_details=None,
            output_tokens_details=None,
        ),
    )
    service = LLMService([OpenAIAdapter(client=openai_client(response))])

    result = await service.generate("{}", model="gpt-test")

    assert result.finish_reason == "refusal"
    assert result.status == "incomplete"
    assert result.usage.total_tokens == 7


async def test_provider_errors_are_normalized_without_retrying_in_module():
    class RateLimitError(Exception):
        status_code = 429
        request_id = "req_rate_limited"

    client = openai_client(SimpleNamespace())
    client.responses.create.side_effect = RateLimitError("slow down")
    service = LLMService([OpenAIAdapter(client=client)])

    with pytest.raises(LLMError) as caught:
        await service.generate("{}", model="gpt-test")

    assert caught.value.kind is LLMErrorKind.RATE_LIMIT
    assert caught.value.retryable is True
    assert caught.value.request_id == "req_rate_limited"
    client.responses.create.assert_awaited_once()


async def test_configured_model_options_and_client_shutdown():
    openai = OpenAIAdapter(
        client=openai_client(SimpleNamespace()),
        model_reasoning_efforts={"gpt-test": {"low", "high"}},
    )
    anthropic = AnthropicAdapter(
        client=anthropic_client(SimpleNamespace()),
        model_reasoning_efforts={"claude-test": {"medium"}},
    )
    service = LLMService([openai, anthropic])

    assert {option.model for option in service.list_model_options()} == {
        "gpt-test",
        "claude-test",
    }
    await service.aclose()
    openai._client.close.assert_awaited_once()
    anthropic._client.close.assert_awaited_once()


async def test_current_sdk_response_models_match_adapter_extraction():
    openai_response = Response.model_validate(
        {
            "id": "resp_sdk",
            "created_at": 0,
            "model": "gpt-test",
            "object": "response",
            "output": [
                {
                    "id": "msg_sdk",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": "openai", "annotations": []}
                    ],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "status": "completed",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 2,
                "total_tokens": 12,
                "input_tokens_details": {
                    "cached_tokens": 3,
                    "cache_write_tokens": 0,
                },
                "output_tokens_details": {"reasoning_tokens": 1},
            },
        }
    )
    anthropic_response = Message.model_validate(
        {
            "id": "msg_sdk",
            "content": [{"type": "text", "text": "anthropic", "citations": None}],
            "model": "claude-test",
            "role": "assistant",
            "type": "message",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }
    )

    openai_result = await OpenAIAdapter(
        client=openai_client(openai_response)
    ).generate("{}", model="gpt-test")
    anthropic_result = await AnthropicAdapter(
        client=anthropic_client(anthropic_response)
    ).generate("{}", model="claude-test")

    assert openai_result.content == "openai"
    assert openai_result.usage.cached_input_tokens == 3
    assert anthropic_result.content == "anthropic"
    assert anthropic_result.usage.total_tokens == 12
