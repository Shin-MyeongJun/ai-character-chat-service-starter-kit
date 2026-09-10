from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping

from app.modules.llm.types import (
    LLMError,
    LLMErrorKind,
    LLMProvider,
    LLMResultInfo,
    ModelOptionInfo,
    ReasoningEffort,
    UnsupportedModelError,
    UnsupportedReasoningEffortError,
)


class BaseLLMAdapter(ABC):
    provider: LLMProvider
    model_prefixes: tuple[str, ...] = ()
    provider_reasoning_efforts: frozenset[ReasoningEffort] = frozenset()

    def __init__(
        self,
        *,
        model_reasoning_efforts: Mapping[str, Iterable[ReasoningEffort | str]]
        | None = None,
        default_max_output_tokens: int = 1200,
    ) -> None:
        if default_max_output_tokens < 1:
            raise ValueError("default_max_output_tokens must be positive.")
        self.default_max_output_tokens = default_max_output_tokens
        self._model_reasoning_efforts = (
            {
                model: frozenset(ReasoningEffort(effort) for effort in efforts)
                for model, efforts in model_reasoning_efforts.items()
            }
            if model_reasoning_efforts is not None
            else None
        )

    def supports_model(self, model: str) -> bool:
        if self._model_reasoning_efforts is not None:
            return model in self._model_reasoning_efforts
        return any(model.startswith(prefix) for prefix in self.model_prefixes)

    def model_options(self) -> tuple[ModelOptionInfo, ...]:
        if self._model_reasoning_efforts is None:
            return ()
        return tuple(
            ModelOptionInfo(self.provider, model, efforts)
            for model, efforts in self._model_reasoning_efforts.items()
        )

    def supported_reasoning_efforts(self, model: str) -> frozenset[ReasoningEffort]:
        if not self.supports_model(model):
            raise UnsupportedModelError(
                f"Model {model!r} is not supported by {self.provider.value}."
            )
        if self._model_reasoning_efforts is not None:
            return self._model_reasoning_efforts[model]
        return self.provider_reasoning_efforts

    async def generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResultInfo:
        if not isinstance(request_json, str) or not request_json.strip():
            raise ValueError("request_json must be a non-blank string.")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-blank string.")

        try:
            effort = (
                ReasoningEffort(reasoning_effort)
                if reasoning_effort is not None
                else None
            )
        except ValueError as exc:
            raise UnsupportedReasoningEffortError(
                f"Unknown reasoning effort {reasoning_effort!r}."
            ) from exc
        if effort is not None and effort not in self.supported_reasoning_efforts(model):
            raise UnsupportedReasoningEffortError(
                f"Reasoning effort {effort.value!r} is not supported by model {model!r}."
            )
        if not self.supports_model(model):
            raise UnsupportedModelError(
                f"Model {model!r} is not supported by {self.provider.value}."
            )

        token_limit = (
            self.default_max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )
        if token_limit < 1:
            raise ValueError("max_output_tokens must be positive.")
        return await self._generate(
            request_json,
            model=model,
            reasoning_effort=effort,
            max_output_tokens=token_limit,
        )

    @abstractmethod
    async def _generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
    ) -> LLMResultInfo: ...

    async def aclose(self) -> None:
        return None

    def _map_error(
        self,
        exc: Exception,
        model: str,
        *,
        kind: LLMErrorKind | None = None,
        retryable: bool = False,
    ) -> LLMError:
        """Build the shared error envelope; adapters classify SDK exceptions."""
        status_code = getattr(exc, "status_code", None)
        request_id = getattr(exc, "request_id", None)
        if kind is None:
            if status_code in {401, 403}:
                kind, retryable = LLMErrorKind.AUTHENTICATION, False
            elif status_code == 429:
                kind, retryable = LLMErrorKind.RATE_LIMIT, True
            elif status_code is not None and 400 <= status_code < 500:
                kind, retryable = LLMErrorKind.INVALID_REQUEST, False
            else:
                kind = LLMErrorKind.PROVIDER
                retryable = status_code is None or status_code >= 500
        return LLMError(
            str(exc),
            kind=kind,
            provider=self.provider,
            model=model,
            retryable=retryable,
            request_id=request_id,
            status_code=status_code,
        )
