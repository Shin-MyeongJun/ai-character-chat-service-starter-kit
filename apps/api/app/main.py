# ASGI 조립: DB 세션·미디어 저장소·LLM·답변 복구 작업의 수명을 함께 관리한다.
# create_app(authenticate=...)는 owner 훅만 교체한다. admin/moderator 훅은 별도 연결이 필요하다.
"""ASGI composition. An identity verifier must be supplied by the deployment."""

from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import structlog
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.http import character_dependencies, dependencies, lorebook_dependencies
from app.http.routes import router
from app.modules.asset_storage.service import (
    create_asset_storage_service,
    load_asset_storage_settings,
)
from app.modules.chatting.memory import service as MemoryService
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.prompt import service as PromptService
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.product.service.views.media import ProductMediaService
from app.modules.llm.adapters import (
    AnthropicAdapter,
    MockLLMAdapter,
    OpenAIAdapter,
    VoyageEmbeddingAdapter,
)
from app.modules.llm.service import EmbeddingService, TextGenerationService
from app.use_cases.answers import AnswerConfig, AnswerOrchestrator

logger = structlog.get_logger(__name__)


async def get_database_session(request: Request):
    async with request.app.state.session_factory() as session:
        yield session


def create_app(*, authenticate=None, asset_read_settings=()) -> FastAPI:
    """authenticate is a trusted FastAPI identity dependency, never an owner ID."""

    @asynccontextmanager
    async def lifespan(app):
        template = PromptService.load_template()
        async with AsyncExitStack() as stack:
            engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
            stack.push_async_callback(engine.dispose)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            app.state.session_factory = sessions
            asset_settings = load_asset_storage_settings()
            asset_storage = create_asset_storage_service(asset_settings)
            stack.push_async_callback(asset_storage.aclose)
            storage_settings = (
                asset_settings.test_local
                if asset_settings.storage_kind == "test_local"
                else asset_settings.s3
            )
            read_storages = {}
            for old_settings in asset_read_settings:
                old_config = (
                    old_settings.test_local
                    if old_settings.storage_kind == "test_local"
                    else old_settings.s3
                )
                identity = (str(old_settings.storage_kind), old_config.storage_id)
                if identity in read_storages or identity == (
                    str(asset_settings.storage_kind),
                    storage_settings.storage_id,
                ):
                    raise ValueError("Asset storage identities must be unique.")
                old_storage = create_asset_storage_service(old_settings)
                stack.push_async_callback(old_storage.aclose)
                read_storages[identity] = old_storage
            media = CharacterMediaService(
                sessions,
                asset_storage,
                storage_kind=str(asset_settings.storage_kind),
                storage_id=storage_settings.storage_id,
                read_storages=read_storages,
            )
            app.state.character_media_service = media
            app.state.product_media_service = ProductMediaService(sessions, media)
            adapters = []
            if os.getenv("OPENAI_API_KEY"):
                adapter = OpenAIAdapter(
                    api_key=os.environ["OPENAI_API_KEY"], max_retries=0
                )
                stack.push_async_callback(adapter.aclose)
                adapters.append(adapter)
            if os.getenv("ANTHROPIC_API_KEY"):
                adapter = AnthropicAdapter(
                    api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=0
                )
                stack.push_async_callback(adapter.aclose)
                adapters.append(adapter)
            if os.getenv("LLM_PROVIDER", "mock") == "mock":
                adapters.append(
                    MockLLMAdapter(
                        responder=lambda _: '"안녕하세요." 상대를 바라보며 인사한다.'
                    )
                )
            text = TextGenerationService(adapters)
            embedding_model = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-large-2")
            embedding_adapters = []
            if os.getenv("VOYAGE_API_KEY"):
                embedding = VoyageEmbeddingAdapter(
                    api_key=os.environ["VOYAGE_API_KEY"],
                    timeout=float(os.getenv("VOYAGE_EMBEDDING_TIMEOUT_SECONDS", "30")),
                    max_retries=0,
                    models=(embedding_model,),
                )
                stack.push_async_callback(embedding.aclose)
                embedding_adapters.append(embedding)
            embeddings = EmbeddingService(embedding_adapters)
            dimension = os.getenv("VOYAGE_EMBEDDING_OUTPUT_DIMENSION", "").strip()
            config = AnswerConfig(
                max_prompt_tokens=int(os.getenv("MAX_PROMPT_TOKENS", "8000")),
                response_tokens=int(os.getenv("MAX_RESPONSE_TOKENS", "1200")),
                timeout_seconds=float(os.getenv("ANSWER_TIMEOUT_SECONDS", "90")),
                embedding_model=embedding_model,
                embedding_provider=os.getenv("EMBEDDING_PROVIDER", "voyage"),
                embedding_output_dimension=int(dimension) if dimension else None,
                memory_policy=MemoryTypes.MemoryPolicy(
                    memory_token_budget=int(
                        os.getenv("MEMORY_RETRIEVAL_TOKEN_BUDGET", "1200")
                    ),
                    retrieval_candidates=int(
                        os.getenv("MEMORY_RETRIEVAL_CANDIDATES", "20")
                    ),
                    retrieval_limit=int(os.getenv("MEMORY_RETRIEVAL_LIMIT", "8")),
                    recent_raw_tokens=int(
                        os.getenv("MEMORY_RECENT_RAW_TOKENS", "1200")
                    ),
                    summarization_threshold_tokens=int(
                        os.getenv("MEMORY_SUMMARY_THRESHOLD_TOKENS", "4000")
                    ),
                ),
            )
            orchestrator = AnswerOrchestrator(
                sessions,
                text,
                MemoryService.MemoryRetriever(sessions, embeddings),
                config=config,
                template=template,
            )
            app.state.answer_orchestrator = orchestrator

            async def recover():
                while True:
                    try:
                        await orchestrator.recover_answers()
                    except Exception as exc:  # noqa: BLE001 - keep recovery supervisor alive
                        logger.warning(
                            "answer_recovery_unavailable", error_kind=type(exc).__name__
                        )
                    await asyncio.sleep(15)

            task = asyncio.create_task(recover())
            try:
                yield
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    for hook in (
        dependencies.get_product_session,
        character_dependencies.get_character_session,
        lorebook_dependencies.get_lorebook_session,
    ):
        app.dependency_overrides[hook] = get_database_session
    if authenticate is not None:
        for auth_hook in (
            dependencies.get_current_owner_id,
            character_dependencies.get_current_owner_id,
            lorebook_dependencies.get_current_owner_id,
        ):
            app.dependency_overrides[auth_hook] = authenticate
    return app


app = create_app()
