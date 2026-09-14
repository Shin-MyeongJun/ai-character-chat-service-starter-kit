"""Durable Hypha memory worker.

Run from ``apps/api`` with ``python -m app.memory_worker``. Provider keys and
model names are read from the environment; message bodies are never logged.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
from contextlib import suppress

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.llm.adapters import (
    AnthropicAdapter,
    MockLLMAdapter,
    OpenAIAdapter,
    VoyageEmbeddingAdapter,
)
from app.modules.llm.adapters.protocols import TextGenerationAdapter
from app.modules.llm.service import EmbeddingService, TextGenerationService
from app.use_cases.memory import MemoryModelConfig, process_memory_work

logger = structlog.get_logger(__name__)


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def _policy() -> MemoryTypes.MemoryPolicy:
    return MemoryTypes.MemoryPolicy(
        summarization_threshold_tokens=_int_env(
            "MEMORY_SUMMARY_THRESHOLD_TOKENS", 4000
        ),
        summary_batch_tokens=_int_env("MEMORY_SUMMARY_BATCH_TOKENS", 3000),
        recent_raw_tokens=_int_env("MEMORY_RECENT_RAW_TOKENS", 1200),
        summary_output_tokens=_int_env("MEMORY_SUMMARY_OUTPUT_TOKENS", 700),
        memory_token_budget=_int_env("MEMORY_RETRIEVAL_TOKEN_BUDGET", 1200),
        retrieval_candidates=_int_env("MEMORY_RETRIEVAL_CANDIDATES", 20),
        retrieval_limit=_int_env("MEMORY_RETRIEVAL_LIMIT", 8),
        prompt_version=os.getenv("MEMORY_SUMMARY_PROMPT_VERSION", "hypha-summary-v1"),
    )


def _text_service(provider: str) -> TextGenerationService:
    adapter: TextGenerationAdapter
    if provider == "openai":
        adapter = OpenAIAdapter(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0)
    elif provider == "anthropic":
        adapter = AnthropicAdapter(
            api_key=os.getenv("ANTHROPIC_API_KEY"), max_retries=0
        )
    elif provider == "mock":
        adapter = MockLLMAdapter(
            responder=lambda _: "Mock durable conversation summary."
        )
    else:
        raise ValueError(f"Unsupported MEMORY_SUMMARY_PROVIDER {provider!r}.")
    return TextGenerationService([adapter])


async def run_worker(*, once: bool, concurrency: int, poll_seconds: float) -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    summary_provider = os.getenv(
        "MEMORY_SUMMARY_PROVIDER", os.getenv("LLM_PROVIDER", "mock")
    )
    models = MemoryModelConfig(
        summary_provider=summary_provider,
        summary_model=os.getenv("MEMORY_SUMMARY_MODEL", "mock-memory-summary"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "voyage"),
        embedding_model=os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-large-2"),
        embedding_output_dimension=_optional_int_env(
            "VOYAGE_EMBEDDING_OUTPUT_DIMENSION"
        ),
    )
    text_service = _text_service(summary_provider)
    embedding_service = EmbeddingService(
        [
            VoyageEmbeddingAdapter(
                api_key=os.getenv("VOYAGE_API_KEY"),
                timeout=float(os.getenv("VOYAGE_EMBEDDING_TIMEOUT_SECONDS", "30")),
                max_retries=_int_env("VOYAGE_EMBEDDING_MAX_RETRIES", 0),
                models=(models.embedding_model,),
            )
        ]
    )
    generator = MemoryService.SummaryGenerator(text_service)
    indexer = MemoryService.MemoryIndexer(embedding_service)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    semaphore = asyncio.Semaphore(concurrency)
    active: set[asyncio.Task] = set()

    async def process(work):
        async with semaphore:
            try:
                await process_memory_work(
                    session_factory,
                    work,
                    policy=_policy(),
                    models=models,
                    summary_generator=generator,
                    indexer=indexer,
                )
            except Exception as exc:  # noqa: BLE001 - task boundary must keep worker alive
                logger.warning(
                    "memory_work_failed",
                    conversation_id=str(work.conversation_id),
                    error_kind=type(exc).__name__,
                )

    try:
        while True:
            active = {task for task in active if not task.done()}
            claimed = False
            while len(active) < concurrency:
                async with session_factory() as session:
                    work = await MemoryService.claim_memory_work(
                        session,
                        MemoryTypes.ClaimMemoryWorkCommand(
                            worker_id=worker_id,
                            lease_seconds=_int_env("MEMORY_WORK_LEASE_SECONDS", 300),
                        ),
                    )
                if work is None:
                    break
                claimed = True
                task = asyncio.create_task(process(work))
                active.add(task)
            if once and not claimed:
                if active:
                    await asyncio.gather(*active)
                    active.clear()
                    # A completed claim can requeue itself when new work arrived
                    # while it was running. Drain that durable request as well.
                    continue
                break
            if not claimed:
                await asyncio.sleep(poll_seconds)
            elif active:
                done, _ = await asyncio.wait(
                    active, return_when=asyncio.FIRST_COMPLETED
                )
                active.difference_update(done)
    finally:
        for task in active:
            task.cancel()
        for task in active:
            with suppress(asyncio.CancelledError):
                await task
        await text_service.aclose()
        await embedding_service.aclose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= 32 or args.poll_seconds <= 0:
        parser.error("concurrency must be 1-32 and poll-seconds must be positive")
    asyncio.run(
        run_worker(
            once=args.once,
            concurrency=args.concurrency,
            poll_seconds=args.poll_seconds,
        )
    )
