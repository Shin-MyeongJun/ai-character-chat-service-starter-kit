# 중립 봉투의 system 메시지는 합쳐 별도 인자로, 나머지는 messages로 전달한다.
# text 블록만 답변에 합치며 캐시 생성·읽기 사용량을 포함해 total_tokens를 계산한다.
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import cast

import anthropic

from app.modules.llm.adapters.base import BaseTextGenerationAdapter
from app.modules.llm.adapters.messages import decode_messages
from app.modules.llm.adapters.sdk import (
    AnthropicRequest,
    MessagesClient,
    integer_attribute,
    sequence_attribute,
    string_attribute,
)
from app.modules.llm.adapters.sdk import (
    response_attribute as _attr,
)
from app.modules.llm.types import (
    LLMErrorKind,
    LLMProvider,
    LLMResultInfo,
    ReasoningEffort,
    TokenUsageInfo,
)


class AnthropicAdapter(BaseTextGenerationAdapter):
    provider = LLMProvider.ANTHROPIC
    model_prefixes = ("claude-",)
    provider_reasoning_efforts = frozenset(
        {
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
            ReasoningEffort.XHIGH,
            ReasoningEffort.MAX,
        }
    )

    def __init__(
        self,
        *,
        client: anthropic.AsyncAnthropic | MessagesClient | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 0,
        model_reasoning_efforts: Mapping[str, Iterable[ReasoningEffort | str]]
        | None = None,
        default_max_output_tokens: int = 1200,
    ) -> None:
        super().__init__(
            model_reasoning_efforts=model_reasoning_efforts,
            default_max_output_tokens=default_max_output_tokens,
        )
        if client is None:
            client = anthropic.AsyncAnthropic(
                api_key=api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
        # SDK/injected client calls use the known nonstream request subset below.
        # Preserve existing duck typing and failure behavior for invalid clients.
        self._client = cast(MessagesClient, client)

    async def _generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
    ) -> LLMResultInfo:
        params: AnthropicRequest = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": request_json}],
        }
        messages = decode_messages(request_json)
        if messages is not None:
            params["system"] = "\n\n".join(
                m["content"] for m in messages if m["role"] == "system"
            )
            params["messages"] = [m for m in messages if m["role"] != "system"]
        if reasoning_effort is not None:
            params["output_config"] = {"effort": reasoning_effort.value}
        try:
            provider_response = await self._client.messages.create(**params)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.AUTHENTICATION, retryable=False
            ) from exc
        except anthropic.RateLimitError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.RATE_LIMIT, retryable=True
            ) from exc
        except anthropic.APITimeoutError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.TIMEOUT, retryable=True
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.CONNECTION, retryable=True
            ) from exc
        except Exception as exc:
            raise self._map_error(exc, model) from exc

        usage_raw = _attr(provider_response, "usage")
        input_tokens = integer_attribute(usage_raw, "input_tokens")
        output_tokens = integer_attribute(usage_raw, "output_tokens")
        cache_creation = integer_attribute(usage_raw, "cache_creation_input_tokens")
        cache_read = integer_attribute(usage_raw, "cache_read_input_tokens")
        known_counts = (input_tokens, output_tokens, cache_creation, cache_read)
        total_tokens = (
            sum(value for value in known_counts if value is not None)
            if any(value is not None for value in known_counts)
            else None
        )
        output_details = _attr(usage_raw, "output_tokens_details")
        cache_creation_details = _attr(usage_raw, "cache_creation")
        usage = TokenUsageInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_creation_5m_input_tokens=integer_attribute(
                cache_creation_details, "ephemeral_5m_input_tokens"
            ),
            cache_creation_1h_input_tokens=integer_attribute(
                cache_creation_details, "ephemeral_1h_input_tokens"
            ),
            cache_read_input_tokens=cache_read,
            reasoning_tokens=integer_attribute(output_details, "thinking_tokens"),
        )
        content = "".join(
            string_attribute(block, "text", "") or ""
            for block in (sequence_attribute(provider_response, "content", ()) or ())
            if _attr(block, "type") == "text"
        )
        stop_details = _attr(provider_response, "stop_details")
        finish_reason = string_attribute(stop_details, "type") or string_attribute(
            provider_response, "stop_reason"
        )
        return LLMResultInfo(
            content=content,
            provider=self.provider,
            model=string_attribute(provider_response, "model", model) or model,
            usage=usage,
            response_id=string_attribute(provider_response, "id"),
            request_id=string_attribute(provider_response, "_request_id"),
            status="completed",
            finish_reason=finish_reason,
        )

    async def aclose(self) -> None:
        close: Callable[[], Awaitable[object]] | None = getattr(
            self._client, "close", None
        )
        if close is not None:
            await close()
