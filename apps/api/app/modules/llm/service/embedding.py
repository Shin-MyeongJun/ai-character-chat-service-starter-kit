# 문서 색인과 검색 질의의 임베딩을 별도 어댑터로 전달한다.
# 텍스트 생성 모델 라우팅과 독립적이며, 오류를 그대로 호출자에게 전파한다.
from __future__ import annotations

from collections.abc import Iterable
from typing import Self

from app.modules.llm.adapters.protocols import EmbeddingAdapter
from app.modules.llm.types import (
    EmbeddingProvider,
    EmbeddingResultInfo,
    EmbedTextsCommand,
    UnsupportedEmbeddingModelError,
)


class EmbeddingService:
    """Select embedding adapters independently from text-generation adapters."""

    def __init__(self, adapters: Iterable[EmbeddingAdapter]) -> None:
        self._adapters = tuple(adapters)
        providers = [adapter.provider for adapter in self._adapters]
        if len(providers) != len(set(providers)):
            raise ValueError(
                "Only one embedding adapter may be registered per provider."
            )

    def _resolve_adapter(
        self,
        model: str,
        provider: EmbeddingProvider | str | None,
    ) -> EmbeddingAdapter:
        if provider is not None:
            selected_provider = EmbeddingProvider(provider)
            candidates = [
                adapter
                for adapter in self._adapters
                if adapter.provider == selected_provider
                and adapter.supports_model(model)
            ]
        else:
            candidates = [
                adapter for adapter in self._adapters if adapter.supports_model(model)
            ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError(
                f"Model {model!r} matches multiple embedding adapters; "
                "specify provider explicitly."
            )
        raise UnsupportedEmbeddingModelError(
            f"No embedding adapter is configured for model {model!r}."
        )

    async def embed_texts(self, command: EmbedTextsCommand) -> EmbeddingResultInfo:
        adapter = self._resolve_adapter(command.model, command.provider)
        return await adapter.embed(
            command.texts,
            model=command.model,
            purpose=command.purpose,
            truncation=command.truncation,
            output_dimension=command.output_dimension,
        )

    async def aclose(self) -> None:
        for adapter in self._adapters:
            await adapter.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
