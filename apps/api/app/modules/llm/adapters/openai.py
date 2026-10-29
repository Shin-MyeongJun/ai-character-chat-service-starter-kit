# 중립 메시지 봉투를 Responses 입력으로 변환하고 사용량·거절·종료 사유를 공통 결과에 담는다.
# SDK 호출 예외만 LLMError로 바꾸며, 입력 봉투 검증 오류는 ValueError로 전달한다.
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import cast

import openai

from app.modules.llm.adapters.base import BaseTextGenerationAdapter
from app.modules.llm.adapters.messages import decode_messages
from app.modules.llm.adapters.sdk import (
    OpenAIRequest,
    ResponsesClient,
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


class OpenAIAdapter(BaseTextGenerationAdapter):
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
        client: openai.AsyncOpenAI | ResponsesClient | None = None,
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
        # The installed SDK and injected clients expose responses.create. Its
        # overloads are wider than the request subset used here; keep duck typing.
        self._client = cast(ResponsesClient, client)

    async def _generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
    ) -> LLMResultInfo:
        params: OpenAIRequest = {
            "model": model,
            "input": decode_messages(request_json) or request_json,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        if reasoning_effort is not None:
            params["reasoning"] = {"effort": reasoning_effort.value}
        try:
            provider_response = await self._client.responses.create(**params)
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

        usage_raw = _attr(provider_response, "usage")
        input_details = _attr(usage_raw, "input_tokens_details")
        output_details = _attr(usage_raw, "output_tokens_details")
        usage = TokenUsageInfo(
            input_tokens=integer_attribute(usage_raw, "input_tokens"),
            output_tokens=integer_attribute(usage_raw, "output_tokens"),
            total_tokens=integer_attribute(usage_raw, "total_tokens"),
            cached_input_tokens=integer_attribute(input_details, "cached_tokens"),
            cache_creation_input_tokens=integer_attribute(
                input_details, "cache_write_tokens"
            ),
            reasoning_tokens=integer_attribute(output_details, "reasoning_tokens"),
        )
        status = string_attribute(provider_response, "status")
        incomplete = _attr(provider_response, "incomplete_details")
        finish_reason = string_attribute(incomplete, "reason") if incomplete else status
        if self._contains_refusal(provider_response):
            finish_reason = "refusal"
        return LLMResultInfo(
            content=string_attribute(provider_response, "output_text", "") or "",
            provider=self.provider,
            model=string_attribute(provider_response, "model", model) or model,
            usage=usage,
            response_id=string_attribute(provider_response, "id"),
            request_id=string_attribute(provider_response, "_request_id"),
            status=status,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _contains_refusal(response: object) -> bool:
        for item in sequence_attribute(response, "output", ()) or ():
            for block in sequence_attribute(item, "content", ()) or ():
                if _attr(block, "type") == "refusal":
                    return True
        return False

    async def aclose(self) -> None:
        close: Callable[[], Awaitable[object]] | None = getattr(
            self._client, "close", None
        )
        if close is not None:
            await close()
