from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from app.modules.llm.adapters.base import BaseLLMAdapter
from app.modules.llm.types import (
    LLMProvider,
    LLMResult,
    ModelOption,
    ReasoningEffort,
    UnsupportedModelError,
)


class LLMService:
    """Select a configured provider adapter and return a normalized result."""

    def __init__(self, adapters: Iterable[BaseLLMAdapter]) -> None:
        self._adapters = tuple(adapters)
        providers = [adapter.provider for adapter in self._adapters]
        if len(providers) != len(set(providers)):
            raise ValueError("Only one adapter may be registered per provider.")

    def list_model_options(self) -> tuple[ModelOption, ...]:
        return tuple(
            option
            for adapter in self._adapters
            for option in adapter.model_options()
        )

    def _resolve_adapter(
        self,
        model: str,
        provider: LLMProvider | str | None,
    ) -> BaseLLMAdapter:
        if provider is not None:
            selected_provider = LLMProvider(provider)
            candidates = [
                adapter
                for adapter in self._adapters
                if adapter.provider == selected_provider and adapter.supports_model(model)
            ]
        else:
            candidates = [
                adapter for adapter in self._adapters if adapter.supports_model(model)
            ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError(
                f"Model {model!r} matches multiple adapters; specify provider explicitly."
            )
        raise UnsupportedModelError(f"No adapter is configured for model {model!r}.")

    async def generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | str | None = None,
        max_output_tokens: int | None = None,
        provider: LLMProvider | str | None = None,
    ) -> LLMResult:
        adapter = self._resolve_adapter(model, provider)
        return await adapter.generate(
            request_json,
            model=model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        )

    async def aclose(self) -> None:
        for adapter in self._adapters:
            await adapter.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
