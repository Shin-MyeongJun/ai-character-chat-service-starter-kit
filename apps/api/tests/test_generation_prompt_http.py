"""Admin prompt HTTP, authorization, projection and SQL scope without an external provider."""

import hashlib
from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.http.dependencies import get_current_owner_id, get_product_session
from app.main import create_app
from app.modules.chatting.chat import repository as ChatRepository
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import prompts as ChatPromptsQueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService
from app.modules.reporting.operations_reporting.service import prompts as PromptsService
from sqlalchemy.dialects import postgresql


def prompt_detail(recorded=True):
    now = datetime(2026, 10, 20, 3, tzinfo=UTC)
    raw = '{ "messages": [{"role":"system","content":"비공개 지침\\n"}], "chat_message_format":1 }'
    summary = ChatTypes.GenerationPromptSummaryInfo(
        uuid4(),
        uuid4(),
        uuid4(),
        "model-at-generation",
        "none",
        "failed",
        now,
        now,
        None,
        recorded,
        now if recorded else None,
        "openai" if recorded else None,
    )
    prompt = (
        ChatTypes.GenerationPromptInfo(
            raw,
            hashlib.sha256(raw.encode()).hexdigest(),
            1,
            now,
            "openai",
            1200,
        )
        if recorded
        else None
    )
    return ChatTypes.GenerationPromptDetailInfo(summary, prompt)


@pytest.fixture
def prompt_http(monkeypatch):
    app = create_app()
    session = SimpleNamespace(no_autoflush=nullcontext())
    actor = uuid4()
    app.dependency_overrides[get_product_session] = lambda: session
    app.dependency_overrides[get_current_owner_id] = lambda: actor
    # Identity repository is mocked, so the actual require_admin policy runs.
    user = SimpleNamespace(id=actor, role="admin", status="active")
    monkeypatch.setattr(
        IdentityQueryService.Repository, "get_user", AsyncMock(return_value=user)
    )
    monkeypatch.setattr(
        IdentityQueryService.PersistenceMapper,
        "user_entity_to_access_info",
        lambda value: (
            None
            if value is None
            else IdentityTypes.UserAccessInfo(value.id, value.role, value.status)
        ),
    )
    return app, actor, user


@pytest.mark.asyncio
async def test_list_projects_only_metadata_and_maps_period_filters_pagination(
    prompt_http, monkeypatch
):
    app, actor, _ = prompt_http
    detail = prompt_detail()
    query = AsyncMock(
        return_value=ChatTypes.GenerationPromptPageInfo((detail.generation,), 8)
    )
    monkeypatch.setattr(ChatPromptsQueryService, "list_generation_prompts", query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/admin/reporting/generation-prompts",
            params={
                "date_from": "2026-10-20",
                "date_to": "2026-10-20",
                "conversation_id": str(detail.generation.conversation_id),
                "status": "failed",
                "page": 2,
                "page_size": 3,
            },
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["page"], body["page_size"], body["total"]) == (2, 3, 8)
    assert body["items"][0]["prompt_recorded"]
    assert (
        not {"request_json", "answer_metadata", "digest", "api_key"}
        & body["items"][0].keys()
    )
    command = query.await_args.args[1]
    assert command.actor_id == actor and command.status == "failed"
    assert command.conversation_id == detail.generation.conversation_id
    assert command.start == datetime(2026, 10, 19, 15, tzinfo=UTC)
    assert command.end == datetime(2026, 10, 20, 15, tzinfo=UTC)
    assert (command.offset, command.limit) == (3, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("recorded", [True, False])
async def test_detail_preserves_raw_string_and_distinguishes_missing_record(
    prompt_http, monkeypatch, recorded
):
    app, _, _ = prompt_http
    detail = prompt_detail(recorded)
    query = AsyncMock(return_value=detail)
    monkeypatch.setattr(ChatPromptsQueryService, "get_generation_prompt", query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/admin/reporting/generation-prompts/{detail.generation.generation_id}"
        )
    assert response.status_code == 200
    data = response.json()
    assert data["generation"]["prompt_recorded"] is recorded
    if recorded:
        assert data["prompt"]["request_json"] == detail.prompt.request_json
        assert (
            data["prompt"]["digest"]
            == hashlib.sha256(data["prompt"]["request_json"].encode()).hexdigest()
        )
        assert data["prompt"]["format_version"] == 1
        assert data["generation"]["status"] == "failed"
    else:
        assert data["prompt"] is None


@pytest.mark.asyncio
async def test_nonexistent_generation_is_404(prompt_http, monkeypatch):
    app, _, _ = prompt_http
    monkeypatch.setattr(
        ChatPromptsQueryService,
        "get_generation_prompt",
        AsyncMock(side_effect=LookupError()),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get(f"/admin/reporting/generation-prompts/{uuid4()}")
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,status",
    [
        ("user", "active"),
        ("creator", "active"),
        ("moderator", "active"),
        ("admin", "suspended"),
        ("admin", "banned"),
    ],
)
async def test_nonadmin_and_inactive_admin_cannot_reach_chat_queries(
    prompt_http, monkeypatch, role, status
):
    app, _, user = prompt_http
    user.role, user.status = role, status
    listing, detail = AsyncMock(), AsyncMock()
    monkeypatch.setattr(ChatPromptsQueryService, "list_generation_prompts", listing)
    monkeypatch.setattr(ChatPromptsQueryService, "get_generation_prompt", detail)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ["?date_from=2026-10-20&date_to=2026-10-20", f"/{uuid4()}"]:
            response = await client.get("/admin/reporting/generation-prompts" + path)
            assert (
                response.status_code == 403 and response.json()["detail"] == "forbidden"
            )
    listing.assert_not_awaited()
    detail.assert_not_awaited()


@pytest.mark.asyncio
async def test_unverified_identity_rejected_before_service(prompt_http, monkeypatch):
    from fastapi import HTTPException

    app, _, _ = prompt_http

    def unauthorized():
        raise HTTPException(401, "authentication_required")

    app.dependency_overrides[get_current_owner_id] = unauthorized
    query = AsyncMock()
    monkeypatch.setattr(PromptsService, "get_generation_prompt", query)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get(f"/admin/reporting/generation-prompts/{uuid4()}")
        ).status_code == 401
    query.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2026-10-21", "date_to": "2026-10-20"},
        {"date_from": "2023-10-21", "date_to": "2026-10-20"},
        {"date_from": "2026-10-20", "date_to": "2026-10-20", "page": 0},
        {"date_from": "2026-10-20", "date_to": "2026-10-20", "page_size": 101},
        {"date_from": "2026-10-20", "date_to": "2026-10-20", "status": "unknown"},
    ],
)
async def test_invalid_filters_rejected(prompt_http, params):
    app, _, _ = prompt_http
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.get("/admin/reporting/generation-prompts", params=params)
        ).status_code == 422


@pytest.mark.asyncio
async def test_list_sql_excludes_raw_and_filters_before_paging():
    statements = []

    class Session:
        async def scalar(self, stmt):
            statements.append(stmt)
            return 0

        async def execute(self, stmt):
            statements.append(stmt)
            return SimpleNamespace(all=list)

    now = datetime.now(UTC)
    cid = uuid4()
    await ChatRepository.list_generation_prompts(
        Session(),
        start=now,
        end=now,
        conversation_id=cid,
        status="failed",
        limit=4,
        offset=8,
    )
    for stmt in statements:
        compiled = stmt.compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert "request_json" not in sql and "answer_metadata" not in sql
        assert "created_at >=" in sql and "created_at <" in sql
        assert "conversation_id =" in sql and "status =" in sql
        assert cid in compiled.params.values() and "failed" in compiled.params.values()
    assert (
        "ORDER BY product_generations.created_at DESC, product_generations.id DESC"
        in str(statements[1])
    )
