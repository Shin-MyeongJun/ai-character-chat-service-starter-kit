# 텍스트 생성과 임베딩의 비동기 호출·종료 경계다. DB 모델 등록과 독립적인 지원 모델 검사를 제공한다.
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.modules.llm.types import (
    EmbeddingProvider,
    EmbeddingPurpose,
    EmbeddingResultInfo,
    LLMProvider,
    LLMResultInfo,
    ModelOptionInfo,
    ReasoningEffort,
)


@runtime_checkable
class TextGenerationAdapter(Protocol):
    """Provider-neutral contract used by every text-generation use case."""

    provider: LLMProvider

    def supports_model(self, model: str) -> bool: ...

    def model_options(self) -> tuple[ModelOptionInfo, ...]: ...

    def supported_reasoning_efforts(self, model: str) -> frozenset[ReasoningEffort]: ...

    async def generate(
        self,
        request_json: str,
        *,
        model: str,
        reasoning_effort: ReasoningEffort | str | None = None,
        max_output_tokens: int | None = None,
    ) -> LLMResultInfo: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class EmbeddingAdapter(Protocol):
    """Provider-neutral embedding contract, independent of text generation."""

    provider: EmbeddingProvider

    def supports_model(self, model: str) -> bool: ...

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        purpose: EmbeddingPurpose | str,
        truncation: bool = False,
        output_dimension: int | None = None,
    ) -> EmbeddingResultInfo: ...

    async def aclose(self) -> None: ...
