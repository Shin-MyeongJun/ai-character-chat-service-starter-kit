from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voyageai import error as voyage_error

from app.modules.llm import (
    EmbeddingError,
    EmbeddingErrorKind,
    EmbeddingProvider,
    EmbeddingPurpose,
    EmbeddingService,
    EmbedTextsCommand,
)
from app.modules.llm.adapters import EmbeddingAdapter, VoyageEmbeddingAdapter

pytestmark = pytest.mark.asyncio

MODEL = "voyage-large-2"


def voyage_client(response):
    return SimpleNamespace(embed=AsyncMock(return_value=response), close=AsyncMock())


@pytest.mark.parametrize("purpose", [EmbeddingPurpose.QUERY, "document"])
async def test_voyage_success_preserves_order_purpose_dimension_and_usage(purpose):
    response = SimpleNamespace(
        embeddings=[[1, 2.5, 3], [-1.0, 0.0, 4.0]], total_tokens=17
    )
    client = voyage_client(response)
    adapter = VoyageEmbeddingAdapter(client=client, models=(MODEL,))
    service = EmbeddingService([adapter])

    result = await service.embed_texts(
        EmbedTextsCommand(
            texts=("first", "second"),
            model=MODEL,
            purpose=purpose,
            provider=EmbeddingProvider.VOYAGE,
        )
    )

    assert isinstance(adapter, EmbeddingAdapter)
    assert result.embeddings == ((1.0, 2.5, 3.0), (-1.0, 0.0, 4.0))
    assert result.dimension == 3
    assert result.model == MODEL
    assert result.provider is EmbeddingProvider.VOYAGE
    assert result.usage.total_tokens == 17
    assert client.embed.await_args.kwargs == {
        "model": MODEL,
        "input_type": EmbeddingPurpose(purpose).value,
        "truncation": False,
        "output_dtype": "float",
        "output_dimension": None,
    }
    assert client.embed.await_args.args == (["first", "second"],)


@pytest.mark.parametrize(
    "texts,kwargs,error",
    [
        ((), {}, ValueError),
        (("",), {}, ValueError),
        (("ok",), {"model": "voyage-other"}, ValueError),
        (("ok",), {"purpose": "classification"}, ValueError),
        (("ok",), {"output_dimension": 0}, ValueError),
        (("ok",) * 1001, {}, ValueError),
    ],
)
async def test_voyage_request_validation_precedes_provider(texts, kwargs, error):
    client = voyage_client(SimpleNamespace())
    adapter = VoyageEmbeddingAdapter(client=client, models=(MODEL,))
    params = {"model": MODEL, "purpose": "query", **kwargs}

    with pytest.raises(error):
        await adapter.embed(texts, **params)

    client.embed.assert_not_awaited()


@pytest.mark.parametrize(
    "response,texts,message",
    [
        (SimpleNamespace(embeddings=None, total_tokens=1), ("one",), "Missing"),
        (SimpleNamespace(embeddings=[], total_tokens=1), ("one",), "count"),
        (
            SimpleNamespace(embeddings=[[1.0], [2.0]], total_tokens=1),
            ("one",),
            "count",
        ),
        (SimpleNamespace(embeddings=[[]], total_tokens=1), ("one",), "empty"),
        (
            SimpleNamespace(embeddings=[[1.0, float("nan")]], total_tokens=1),
            ("one",),
            "finite",
        ),
        (
            SimpleNamespace(embeddings=[[1.0], [1.0, 2.0]], total_tokens=1),
            ("one", "two"),
            "inconsistent",
        ),
        (SimpleNamespace(embeddings=[[1.0]], total_tokens=-1), ("one",), "usage"),
    ],
)
async def test_voyage_invalid_responses_are_explicit(response, texts, message):
    adapter = VoyageEmbeddingAdapter(client=voyage_client(response), models=(MODEL,))

    with pytest.raises(EmbeddingError, match=message) as caught:
        await adapter.embed(texts, model=MODEL, purpose="document")

    assert caught.value.kind is EmbeddingErrorKind.INVALID_RESPONSE
    assert caught.value.retryable is False


@pytest.mark.parametrize(
    "provider_error,kind,retryable",
    [
        (
            voyage_error.AuthenticationError(
                "bad key", http_status=401, headers={"request-id": "req-auth"}
            ),
            EmbeddingErrorKind.AUTHENTICATION,
            False,
        ),
        (
            voyage_error.RateLimitError("slow", http_status=429),
            EmbeddingErrorKind.RATE_LIMIT,
            True,
        ),
        (voyage_error.Timeout("late"), EmbeddingErrorKind.TIMEOUT, True),
        (
            voyage_error.InvalidRequestError("bad", http_status=400),
            EmbeddingErrorKind.INVALID_REQUEST,
            False,
        ),
    ],
)
async def test_voyage_errors_are_normalized_without_adapter_retry(
    provider_error, kind, retryable
):
    client = voyage_client(None)
    client.embed.side_effect = provider_error
    adapter = VoyageEmbeddingAdapter(client=client, models=(MODEL,))

    with pytest.raises(EmbeddingError) as caught:
        await adapter.embed(("query",), model=MODEL, purpose="query")

    assert caught.value.kind is kind
    assert caught.value.retryable is retryable
    assert caught.value.status_code == getattr(provider_error, "http_status", None)
    assert caught.value.request_id == getattr(provider_error, "request_id", None)
    client.embed.assert_awaited_once()


async def test_injected_client_remains_caller_owned():
    client = voyage_client(SimpleNamespace(embeddings=[[1.0]], total_tokens=1))
    adapter = VoyageEmbeddingAdapter(client=client, models=(MODEL,))

    await adapter.aclose()

    client.close.assert_not_awaited()


async def test_owned_client_receives_config_and_is_closed_when_supported(monkeypatch):
    created = SimpleNamespace(kwargs=None, aclose=AsyncMock())

    def client_factory(**kwargs):
        created.kwargs = kwargs
        return created

    monkeypatch.setattr(
        "app.modules.llm.adapters.voyage.voyageai.AsyncClient", client_factory
    )
    adapter = VoyageEmbeddingAdapter(
        api_key="secret",
        timeout=12.5,
        max_retries=2,
        models=(MODEL,),
    )

    assert created.kwargs == {
        "api_key": "secret",
        "timeout": 12.5,
        "max_retries": 2,
    }
    await adapter.aclose()
    created.aclose.assert_awaited_once()
