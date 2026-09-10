from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import openai

from app.modules.llm.adapters.base import BaseLLMAdapter
from app.modules.llm.types import (
    LLMErrorKind,
    LLMProvider,
    LLMResultInfo,
    ReasoningEffort,
    TokenUsageInfo,
)


def _attr(value: object | None, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAIAdapter(BaseLLMAdapter):
    provider = LLMProvider.OPENAI
    model_prefixes = ("gpt-", "o1", "o3", "o4")
    provider_reasoning_efforts = frozenset(
        {
            ReasoningEffort.NONE,
            ReasoningEffort.MINIMAL,
            ReasoningEffort.LOW,
            ReasoningEffort.MEDIUM,
            ReasoningEffort.HIGH,
            ReasoningEffort.XHIGH,
        }
    )

    def __init__(
        self,
        *,
        client: Any | None = None,
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
            client = openai.AsyncOpenAI(
                api_key=api_key,
                timeout=timeout,
                max_retries=max_retries,
            )
        self._client = client

    async def _generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
    ) -> LLMResultInfo:
        params: dict[str, Any] = {
            "model": model,
            "input": request_json,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if reasoning_effort is not None:
            params["reasoning"] = {"effort": reasoning_effort.value}
        try:
            response = await self._client.responses.create(**params)
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.AUTHENTICATION, retryable=False
            ) from exc
        except openai.RateLimitError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.RATE_LIMIT, retryable=True
            ) from exc
        except openai.APITimeoutError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.TIMEOUT, retryable=True
            ) from exc
        except openai.APIConnectionError as exc:
            raise self._map_error(
                exc, model, kind=LLMErrorKind.CONNECTION, retryable=True
            ) from exc
        except Exception as exc:
            raise self._map_error(exc, model) from exc

        usage_raw = _attr(response, "usage")
        input_details = _attr(usage_raw, "input_tokens_details")
        output_details = _attr(usage_raw, "output_tokens_details")
        usage = TokenUsageInfo(
            input_tokens=_attr(usage_raw, "input_tokens"),
            output_tokens=_attr(usage_raw, "output_tokens"),
            total_tokens=_attr(usage_raw, "total_tokens"),
            cached_input_tokens=_attr(input_details, "cached_tokens"),
            cache_creation_input_tokens=_attr(input_details, "cache_write_tokens"),
            reasoning_tokens=_attr(output_details, "reasoning_tokens"),
        )
        status = _attr(response, "status")
        incomplete = _attr(response, "incomplete_details")
        finish_reason = _attr(incomplete, "reason") if incomplete else status
        if self._contains_refusal(response):
            finish_reason = "refusal"
        return LLMResultInfo(
            content=_attr(response, "output_text", "") or "",
            provider=self.provider,
            model=_attr(response, "model", model) or model,
            usage=usage,
            response_id=_attr(response, "id"),
            request_id=_attr(response, "_request_id"),
            status=status,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _contains_refusal(response: object) -> bool:
        for item in _attr(response, "output", ()) or ():
            for block in _attr(item, "content", ()) or ():
                if _attr(block, "type") == "refusal":
                    return True
        return False

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()
