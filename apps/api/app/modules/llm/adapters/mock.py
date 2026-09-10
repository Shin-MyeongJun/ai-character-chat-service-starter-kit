from __future__ import annotations

from collections.abc import Callable

from app.modules.llm.adapters.base import BaseLLMAdapter
from app.modules.llm.types import (
    LLMProvider,
    LLMResultInfo,
    ReasoningEffort,
    TokenUsageInfo,
)


class MockLLMAdapter(BaseLLMAdapter):
    provider = LLMProvider.MOCK
    model_prefixes = ("mock-",)

    def __init__(
        self,
        responder: Callable[[str], str] | None = None,
        *,
        default_max_output_tokens: int = 1200,
    ) -> None:
        super().__init__(default_max_output_tokens=default_max_output_tokens)
        self._responder = responder or (lambda request_json: request_json)

    async def _generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
    ) -> LLMResultInfo:
        return LLMResultInfo(
            content=self._responder(request_json),
            provider=self.provider,
            model=model,
            usage=TokenUsageInfo(0, 0, 0),
            status="completed",
            finish_reason="mock",
        )
