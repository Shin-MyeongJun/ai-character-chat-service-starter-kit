# VOYAGE_API_KEY가 있으면 실제 외부 호출을 수행하는 검사다. 키가 없으면 skip한다.
"""Opt-in live check; unit tests use mocks and never consume Voyage API quota."""

import os

import pytest

from app.modules.llm import EmbeddingPurpose
from app.modules.llm.adapters import VoyageEmbeddingAdapter


@pytest.mark.asyncio
async def test_voyage_live_embedding():
    api_key = os.getenv("VOYAGE_API_KEY")
    if not api_key:
        pytest.skip("VOYAGE_API_KEY is required for the live Voyage check.")
    model = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-large-2")
    timeout = float(os.getenv("VOYAGE_EMBEDDING_TIMEOUT_SECONDS", "30"))
    max_retries = int(os.getenv("VOYAGE_EMBEDDING_MAX_RETRIES", "0"))
    adapter = VoyageEmbeddingAdapter(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        models=(model,),
    )

    result = await adapter.embed(
        ("Voyage live embedding health check.",),
        model=model,
        purpose=EmbeddingPurpose.QUERY,
    )

    assert len(result.embeddings) == 1
    assert result.dimension > 0
    assert result.usage.total_tokens is not None
