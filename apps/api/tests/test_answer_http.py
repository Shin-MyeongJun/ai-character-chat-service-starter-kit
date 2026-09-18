# HTTP 상태·인증 훅·수명 정리를 mock으로 확인한다. 실제 DB/공급자 성공 검증과 구분한다.
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from app.http.answers import get_answer_orchestrator, router
from app.http.dependencies import get_current_owner_id
from app.main import create_app
from app.use_cases.answers import AnswerInfo, AnswerStorageError
from fastapi import FastAPI


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,http_status",
    [
        ("succeeded", None, 200),
        ("pending", None, 202),
        ("failed", "llm_rate_limit", 429),
        ("failed", "llm_authentication", 502),
        ("failed", "timeout", 504),
        ("failed", "fixed_context_exceeded", 422),
        ("failed", "summary_required", 409),
        ("stale", "stale", 409),
    ],
)
async def test_http_answer_contract(status, code, http_status):
    app = FastAPI()
    app.include_router(router)
    owner = uuid4()
    app.dependency_overrides[get_current_owner_id] = lambda: owner
    value = AnswerInfo(
        uuid4(),
        status,
        "완성 답변" if status == "succeeded" else None,
        "gpt-test",
        code,
        False,
        False,
    )
    orchestrator = SimpleNamespace(generate_answer=AsyncMock(return_value=value))
    app.dependency_overrides[get_answer_orchestrator] = lambda: orchestrator
    body = {
        "request_key": "answer-1",
        "input_message_id": str(uuid4()),
        "expected_revision": 1,
        "product_character_id": str(uuid4()),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/conversations/{uuid4()}/answers", json=body)
    assert response.status_code == http_status
    assert response.json()["generation_id"] == str(value.generation_id)
    assert orchestrator.generate_answer.await_args.args[0].user_id == owner
    if status == "pending":
        assert response.headers["retry-after"] == "3"


@pytest.mark.asyncio
async def test_unconfigured_auth_and_owner_spoofing_are_rejected():
    app = create_app()
    runtime = SimpleNamespace(generate_answer=AsyncMock())
    app.dependency_overrides[get_answer_orchestrator] = lambda: runtime
    body = {
        "request_key": "a",
        "input_message_id": str(uuid4()),
        "expected_revision": 1,
        "product_character_id": str(uuid4()),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.post(
                f"/conversations/{uuid4()}/answers",
                json=body,
                headers={"X-Owner-ID": str(uuid4())},
            )
        ).status_code == 503
        app.dependency_overrides[get_current_owner_id] = lambda: uuid4()
        assert (
            await client.post(
                f"/conversations/{uuid4()}/answers",
                json={**body, "owner_id": str(uuid4())},
            )
        ).status_code == 422
    runtime.generate_answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_error_returns_same_key_retry_instruction():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_owner_id] = lambda: uuid4()
    app.dependency_overrides[get_answer_orchestrator] = lambda: SimpleNamespace(
        generate_answer=AsyncMock(side_effect=AnswerStorageError("private db error"))
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/conversations/{uuid4()}/answers",
            json={
                "request_key": "a",
                "input_message_id": str(uuid4()),
                "expected_revision": 1,
                "product_character_id": str(uuid4()),
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "storage_pending_recovery",
        "retry_same_key": True,
    }


@pytest.mark.asyncio
async def test_lifespan_connects_sessions_and_closes_owned_clients(
    monkeypatch, tmp_path
):
    from app import main

    engine = SimpleNamespace(dispose=AsyncMock())
    adapter = SimpleNamespace(provider="openai", aclose=AsyncMock())
    embedding = SimpleNamespace(provider="voyage", aclose=AsyncMock())
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setenv("ASSET_STORAGE_KIND", "test_local")
    monkeypatch.setenv("ASSET_TEST_LOCAL_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    # 인증도 앱 수명에 함께 조립되므로 실제 비밀값 대신 실행마다 만든 테스트 키를 주입한다.
    import base64
    import secrets

    from cryptography.fernet import Fernet

    monkeypatch.setenv(
        "AUTH_JWT_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
    )
    monkeypatch.setenv("AUTH_FLOW_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SMTP_HOST", "localhost")
    monkeypatch.setenv("SMTP_FROM", "test@example.com")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-only")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(main, "create_async_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(main, "async_sessionmaker", lambda *a, **kw: object())
    monkeypatch.setattr(main, "OpenAIAdapter", lambda **kw: adapter)
    monkeypatch.setattr(main, "VoyageEmbeddingAdapter", lambda **kw: embedding)
    original_storage_factory = main.create_asset_storage_service
    storage_closers = []

    def create_storage(settings):
        service = original_storage_factory(settings)
        closer = AsyncMock(wraps=service.aclose)
        monkeypatch.setattr(service, "aclose", closer)
        storage_closers.append(closer)
        return service

    storage_factory = Mock(side_effect=create_storage)
    monkeypatch.setattr(main, "create_asset_storage_service", storage_factory)
    monkeypatch.setattr(
        main.AnswerOrchestrator, "recover_answers", AsyncMock(return_value=0)
    )
    app = main.create_app()
    async with app.router.lifespan_context(app):
        assert app.state.answer_orchestrator is not None
        assert app.state.session_factory is not None
        assert app.state.authentication is not None
        assert app.state.google_login is not None
        storage_factory.assert_called_once()
        assert (
            app.state.product_media_service.media is app.state.character_media_service
        )
    storage_factory.assert_called_once()
    storage_closers[0].assert_awaited_once()
    engine.dispose.assert_awaited_once()
    adapter.aclose.assert_awaited_once()
    embedding.aclose.assert_awaited_once()
