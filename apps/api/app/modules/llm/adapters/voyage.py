# purpose(query/document)를 Voyage input_type으로 전달한다. 재시도는 SDK 설정에 맡긴다.
# 응답 개수·유한 수치·동일 차원을 검증하지만 요청 차원과의 일치 여부는 여기서 비교하지 않는다.
# 주입받은 client는 닫지 않고, 직접 생성한 client만 종료한다.
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Iterable, Sequence
from math import isfinite
from numbers import Integral, Real
from typing import Any

import voyageai
from voyageai import error as voyage_error

from app.modules.llm.types import (
    EmbeddingError,
    EmbeddingErrorKind,
    EmbeddingProvider,
    EmbeddingPurpose,
    EmbeddingResultInfo,
    EmbeddingUsageInfo,
    UnsupportedEmbeddingModelError,
)


class VoyageEmbeddingAdapter:
    """Async Voyage text-embedding adapter.

    The SDK owns request retries. This adapter and EmbeddingService never retry.
    Injected clients remain caller-owned; a client constructed here is closed only
    when a future SDK version exposes a close method.
    """

    provider = EmbeddingProvider.VOYAGE

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 0,
        models: Iterable[str] = ("voyage-large-2",),
    ) -> None:
        configured_models = tuple(models)
        if not configured_models or any(
            not isinstance(model, str) or not model.strip()
            for model in configured_models
        ):
            raise ValueError("models must contain at least one non-blank model name.")
        if len(configured_models) != len(set(configured_models)):
            raise ValueError("models must not contain duplicates.")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise TypeError("timeout must be a number of seconds.")
        if not isfinite(float(timeout)) or timeout <= 0:
            raise ValueError("timeout must be positive and finite.")
        if not isinstance(max_retries, int) or isinstance(max_retries, bool):
            raise TypeError("max_retries must be an integer.")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative.")

        self._models = frozenset(configured_models)
        self._owns_client = client is None
        if client is None:
            client = voyageai.AsyncClient(
                api_key=api_key,
                timeout=float(timeout),
                max_retries=max_retries,
            )
        self._client = client

    def supports_model(self, model: str) -> bool:
        return model in self._models

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str,
        purpose: EmbeddingPurpose | str,
        truncation: bool = False,
        output_dimension: int | None = None,
    ) -> EmbeddingResultInfo:
        request_texts = self._validate_request(
            texts,
            model=model,
            truncation=truncation,
            output_dimension=output_dimension,
        )
        try:
            selected_purpose = EmbeddingPurpose(purpose)
        except ValueError as exc:
            raise ValueError(f"Unsupported embedding purpose {purpose!r}.") from exc

        try:
            response = await self._client.embed(
                request_texts,
                model=model,
                input_type=selected_purpose.value,
                truncation=truncation,
                output_dtype="float",
                output_dimension=output_dimension,
            )
        except voyage_error.AuthenticationError as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.AUTHENTICATION, retryable=False
            ) from exc
        except voyage_error.RateLimitError as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.RATE_LIMIT, retryable=True
            ) from exc
        except voyage_error.Timeout as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.TIMEOUT, retryable=True
            ) from exc
        except voyage_error.APIConnectionError as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.CONNECTION, retryable=True
            ) from exc
        except (
            voyage_error.InvalidRequestError,
            voyage_error.MalformedRequestError,
        ) as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.INVALID_REQUEST, retryable=False
            ) from exc
        except (
            voyage_error.ServiceUnavailableError,
            voyage_error.ServerError,
            voyage_error.TryAgain,
        ) as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.PROVIDER, retryable=True
            ) from exc
        except voyage_error.VoyageError as exc:
            status_code = getattr(exc, "http_status", None)
            kind = (
                EmbeddingErrorKind.INVALID_REQUEST
                if isinstance(status_code, int) and 400 <= status_code < 500
                else EmbeddingErrorKind.PROVIDER
            )
            raise self._map_error(
                exc,
                model,
                kind,
                retryable=kind is EmbeddingErrorKind.PROVIDER,
            ) from exc
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.TIMEOUT, retryable=True
            ) from exc
        except Exception as exc:
            raise self._map_error(
                exc, model, EmbeddingErrorKind.PROVIDER, retryable=False
            ) from exc

        return self._response_to_info(response, model, len(request_texts))

    def _validate_request(
        self,
        texts: Sequence[str],
        *,
        model: str,
        truncation: bool,
        output_dimension: int | None,
    ) -> list[str]:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-blank string.")
        if not self.supports_model(model):
            raise UnsupportedEmbeddingModelError(
                f"Model {model!r} is not configured for {self.provider.value}."
            )
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise TypeError("texts must be a sequence of strings.")
        request_texts = list(texts)
        if not request_texts:
            raise ValueError("texts must not be empty.")
        if len(request_texts) > 1000:
            raise ValueError("Voyage accepts at most 1000 texts per embedding request.")
        if any(not isinstance(text, str) or not text.strip() for text in request_texts):
            raise ValueError("texts must contain only non-blank strings.")
        if not isinstance(truncation, bool):
            raise TypeError("truncation must be a boolean.")
        if output_dimension is not None and (
            not isinstance(output_dimension, int)
            or isinstance(output_dimension, bool)
            or output_dimension < 1
        ):
            raise ValueError("output_dimension must be a positive integer or None.")
        return request_texts

    def _response_to_info(
        self, response: object, model: str, expected_count: int
    ) -> EmbeddingResultInfo:
        raw_embeddings = getattr(response, "embeddings", None)
        if isinstance(raw_embeddings, (str, bytes)) or not isinstance(
            raw_embeddings, Sequence
        ):
            raise self._invalid_response(model, "Missing embeddings sequence.")
        if len(raw_embeddings) != expected_count:
            raise self._invalid_response(
                model,
                "Embedding response count does not match the input count.",
            )

        vectors: list[tuple[float, ...]] = []
        dimension: int | None = None
        for raw_vector in raw_embeddings:
            if isinstance(raw_vector, (str, bytes)) or not isinstance(
                raw_vector, Sequence
            ):
                raise self._invalid_response(
                    model, "Embedding vector is not a sequence."
                )
            if not raw_vector:
                raise self._invalid_response(
                    model, "Embedding vector must not be empty."
                )
            if any(
                not isinstance(value, Real)
                or isinstance(value, bool)
                or not isfinite(float(value))
                for value in raw_vector
            ):
                raise self._invalid_response(
                    model, "Embedding vector must contain only finite numbers."
                )
            vector = tuple(float(value) for value in raw_vector)
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise self._invalid_response(
                    model, "Embedding vectors have inconsistent dimensions."
                )
            vectors.append(vector)

        total_tokens = getattr(response, "total_tokens", None)
        if total_tokens is not None and (
            not isinstance(total_tokens, Integral)
            or isinstance(total_tokens, bool)
            or total_tokens < 0
        ):
            raise self._invalid_response(model, "Invalid provider token usage.")
        assert dimension is not None
        return EmbeddingResultInfo(
            embeddings=tuple(vectors),
            dimension=dimension,
            provider=self.provider,
            model=model,
            usage=EmbeddingUsageInfo(
                total_tokens=int(total_tokens) if total_tokens is not None else None
            ),
        )

    def _invalid_response(self, model: str, message: str) -> EmbeddingError:
        return EmbeddingError(
            message,
            kind=EmbeddingErrorKind.INVALID_RESPONSE,
            provider=self.provider,
            model=model,
            retryable=False,
        )

    def _map_error(
        self,
        exc: Exception,
        model: str,
        kind: EmbeddingErrorKind,
        *,
        retryable: bool,
    ) -> EmbeddingError:
        return EmbeddingError(
            str(exc),
            kind=kind,
            provider=self.provider,
            model=model,
            retryable=retryable,
            request_id=getattr(exc, "request_id", None),
            status_code=getattr(exc, "http_status", None),
        )

    async def aclose(self) -> None:
        if not self._owns_client:
            return
        close = getattr(self._client, "aclose", None) or getattr(
            self._client, "close", None
        )
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
