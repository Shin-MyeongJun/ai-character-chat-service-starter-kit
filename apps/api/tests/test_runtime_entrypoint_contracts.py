"""Resource and failure contracts with engine/storage/provider/service doubles."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession
from test_identity_security import auth_settings as auth_settings_fixture

from app import auth_cleanup, main, media_cleanup, memory_worker
from app.modules.asset_storage.service.settings import load_asset_storage_settings
from app.modules.asset_storage.types import AssetStorageSettings
from app.modules.chatting.memory.types import MemoryWorkInfo
from app.modules.content.character.types import CleanupCharacterMediaInfo
from app.modules.identity.settings import AuthSettings
from app.modules.identity.types import CleanupInfo

auth_settings = auth_settings_fixture


def storage_settings(identity: str) -> AssetStorageSettings:
    return load_asset_storage_settings(
        {
            "ENVIRONMENT": "test",
            "ASSET_STORAGE_KIND": "test_local",
            "ASSET_STORAGE_ID": identity,
            "ASSET_TEST_LOCAL_ROOT": str(Path.cwd() / "unused-runtime-storage"),
        }
    )


def resource(name: str, events: list[str]) -> MagicMock:
    item = MagicMock()

    async def close() -> None:
        events.append(name)

    item.aclose = AsyncMock(side_effect=close)
    item.dispose = item.aclose
    return item


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["auth", "duplicate", "none"])
async def test_lifespan_unwinds_owned_resources_and_stops_recovery_first(
    monkeypatch: pytest.MonkeyPatch,
    auth_settings: AuthSettings,
    failure: str,
) -> None:
    events: list[str] = []
    engine = resource("engine", events)
    current, old = storage_settings("current"), storage_settings("old")
    stores = {"current": resource("current", events), "old": resource("old", events)}
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(main, "create_async_engine", MagicMock(return_value=engine))
    monkeypatch.setattr(main, "async_sessionmaker", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        main,
        "load_auth_settings",
        MagicMock(
            return_value=auth_settings,
            side_effect=ValueError("invalid config") if failure == "auth" else None,
        ),
    )
    monkeypatch.setattr(
        main, "load_asset_storage_settings", MagicMock(return_value=current)
    )

    def create_storage(settings: AssetStorageSettings) -> MagicMock:
        assert settings.test_local is not None
        return stores[settings.test_local.storage_id]

    monkeypatch.setattr(main, "create_asset_storage_service", create_storage)
    for env, constructor, provider in (
        ("OPENAI_API_KEY", "OpenAIAdapter", "openai"),
        ("ANTHROPIC_API_KEY", "AnthropicAdapter", "anthropic"),
        ("VOYAGE_API_KEY", "VoyageEmbeddingAdapter", "voyage"),
    ):
        monkeypatch.setenv(env, "test-only")
        adapter = resource(provider, events)
        adapter.provider = provider
        monkeypatch.setattr(main, constructor, MagicMock(return_value=adapter))
    entered = asyncio.Event()

    async def recover(self: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("recovery-stopped")

    monkeypatch.setattr(main.AnswerOrchestrator, "recover_answers", recover)
    historical = iter((old, old)) if failure == "duplicate" else iter((old,))
    app = main.create_app(asset_read_settings=historical)
    if failure != "none":
        with pytest.raises(ValueError):
            async with app.router.lifespan_context(app):
                pytest.fail("Startup failure must not yield")
        assert events == (
            ["engine"] if failure == "auth" else ["old", "current", "engine"]
        )
    else:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(entered.wait(), timeout=2)
            assert not events
            assert app.state.authentication is not None
        assert events == [
            "recovery-stopped",
            "voyage",
            "anthropic",
            "openai",
            "old",
            "current",
            "engine",
        ]


@pytest.mark.asyncio
async def test_session_dependency_closes_factory_context_on_consumer_error() -> None:
    events: list[str] = []

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            events.append("open")
            try:
                yield session
            finally:
                events.append("close")

    app = FastAPI()
    app.state.session_factory = factory
    request = Request({"type": "http", "app": app})
    with pytest.raises(RuntimeError, match="consumer failed"):
        async with asynccontextmanager(main.get_database_session)(request) as session:
            assert isinstance(session, AsyncSession)
            raise RuntimeError("consumer failed")
    assert events == ["open", "close"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first", [False, True])
async def test_worker_once_drains_work_and_closes_clients_after_task_failures(
    monkeypatch: pytest.MonkeyPatch,
    fail_first: bool,
) -> None:
    events: list[str] = []
    engine = resource("engine", events)
    text, embedding = resource("text", events), resource("embedding", events)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(
        memory_worker, "create_async_engine", MagicMock(return_value=engine)
    )
    monkeypatch.setattr(
        memory_worker, "async_sessionmaker", MagicMock(return_value=AsyncSession)
    )
    monkeypatch.setattr(memory_worker, "_text_service", MagicMock(return_value=text))
    monkeypatch.setattr(memory_worker, "VoyageEmbeddingAdapter", MagicMock())
    monkeypatch.setattr(
        memory_worker, "EmbeddingService", MagicMock(return_value=embedding)
    )
    jobs = [
        MemoryWorkInfo(uuid4(), uuid4(), 1, 1, "worker", claim_token=uuid4())
        for _ in range(2)
    ]
    queue = iter(jobs)

    async def claim(*args: object) -> MemoryWorkInfo | None:
        return next(queue, None)

    async def process(*args: object, **kwargs: object) -> None:
        events.append("process")
        if fail_first and events.count("process") == 1:
            raise RuntimeError("job failure")

    operation = AsyncMock(side_effect=process)
    monkeypatch.setattr(
        memory_worker.MemoryService, "claim_memory_work", AsyncMock(side_effect=claim)
    )
    monkeypatch.setattr(memory_worker, "process_memory_work", operation)
    await memory_worker.run_worker(once=True, concurrency=1, poll_seconds=0.01)
    assert events == ["process", "process", "text", "embedding", "engine"]
    assert [call.args[1].work for call in operation.await_args_list] == jobs


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first", [False, True])
async def test_media_cleanup_continues_explicit_ids_and_reports_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fail_first: bool,
) -> None:
    events: list[str] = []
    engine, storage = resource("engine", events), resource("storage", events)
    storage.__aenter__ = AsyncMock(return_value=storage)

    # __aexit__ receives exception metadata, so use a dedicated async exit.
    async def exit_storage(*args: object) -> None:
        await storage.aclose()

    storage.__aexit__ = AsyncMock(side_effect=exit_storage)
    operation = AsyncMock(
        side_effect=[
            RuntimeError("secret details")
            if fail_first
            else CleanupCharacterMediaInfo(True, "deleted"),
            CleanupCharacterMediaInfo(False, "still_referenced"),
        ]
    )
    service = MagicMock(cleanup_character_media=operation)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(
        media_cleanup, "create_async_engine", MagicMock(return_value=engine)
    )
    monkeypatch.setattr(
        media_cleanup, "async_sessionmaker", MagicMock(return_value=AsyncSession)
    )
    monkeypatch.setattr(
        media_cleanup,
        "load_asset_storage_settings",
        MagicMock(return_value=storage_settings("current")),
    )
    monkeypatch.setattr(
        media_cleanup, "create_asset_storage_service", MagicMock(return_value=storage)
    )
    monkeypatch.setattr(
        media_cleanup, "CharacterMediaWorkflow", MagicMock(return_value=service)
    )
    ids, cutoff = [uuid4(), uuid4()], datetime.now(UTC)
    assert await media_cleanup.run_cleanup(iter(ids), cutoff) == int(fail_first)
    assert [call.args[0].media_id for call in operation.await_args_list] == ids
    assert all(call.args[0].older_than == cutoff for call in operation.await_args_list)
    assert events == ["storage", "engine"]
    output = capsys.readouterr().out
    assert "secret details" not in output
    assert "still_referenced" in output


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["none", "settings", "service"])
async def test_auth_cleanup_always_disposes_engine_and_preserves_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    auth_settings: AuthSettings,
    failure: str,
) -> None:
    events: list[str] = []
    engine = resource("engine", events)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(
        auth_cleanup, "create_async_engine", MagicMock(return_value=engine)
    )
    monkeypatch.setattr(
        auth_cleanup, "async_sessionmaker", MagicMock(return_value=AsyncSession)
    )
    monkeypatch.setattr(
        auth_cleanup,
        "load_auth_settings",
        MagicMock(
            return_value=auth_settings,
            side_effect=ValueError("settings failed")
            if failure == "settings"
            else None,
        ),
    )
    operation = AsyncMock(
        return_value=CleanupInfo(1, 2, 3, 4, 5),
        side_effect=RuntimeError("cleanup failed") if failure == "service" else None,
    )
    monkeypatch.setattr(
        auth_cleanup,
        "AuthenticationService",
        MagicMock(return_value=MagicMock(cleanup_expired_auth=operation)),
    )
    if failure == "none":
        await auth_cleanup.main()
        assert "CleanupInfo(" in capsys.readouterr().out
    else:
        with pytest.raises(ValueError if failure == "settings" else RuntimeError):
            await auth_cleanup.main()
        assert not capsys.readouterr().out
    assert events == ["engine"]
