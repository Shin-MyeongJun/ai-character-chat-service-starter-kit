"""Regression checks for the existing HTTP/application/persistence boundaries."""

import ast
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import get_args, get_origin
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.chatting.conversation import service as conversation_service
from app.modules.chatting.conversation import types as conversation_types
from app.modules.chatting.conversation.router import router as conversations
from app.modules.chatting.conversation.service.command import versions
from app.modules.content.product import types
from app.modules.content.product.dependencies import (
    get_current_owner_id,
    get_product_session,
)
from app.modules.content.product.router import router as products
from app.modules.content.product.service import query, statistics
from app.modules.content.product.service.command import composition, releases, settings
from app.modules.content.product.service.views import notices
from app.modules.governance.admin import types as admin_types
from app.modules.governance.admin.model_router import router as model_admin
from app.modules.governance.admin.product_router import router as product_admin
from app.modules.governance.admin.service import command as product_policy
from app.modules.llm.types import ModelNoticeView
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel


@pytest.fixture
def http():
    app = FastAPI()
    for router in (products, conversations, product_admin, model_admin):
        app.include_router(router)
    owner = uuid4()
    session = object()
    app.dependency_overrides[get_current_owner_id] = lambda: owner
    app.dependency_overrides[get_product_session] = lambda: session
    with TestClient(app) as client:
        yield app, client, owner, session


def test_composition_adapter_maps_nested_commands_and_rejects_extra_fields(
    http, monkeypatch
):
    _app, client, owner, session = http
    pid, cid, bid = uuid4(), uuid4(), uuid4()

    async def replace(db, command):
        product_id, owner_id, value = (
            command.product_id,
            command.owner_id,
            command.value,
        )
        assert type(command) is types.ReplaceCompositionCommand
        assert db is session and product_id == pid and owner_id == owner
        assert type(value) is types.ProductCompositionInfo
        assert type(value.characters[0]) is types.CharacterSelection
        assert type(value.lorebooks[0]) is types.LorebookSelection
        assert value.lorebooks[0].character_ids == (cid,)
        return value

    service = AsyncMock(side_effect=replace)
    monkeypatch.setattr(composition, "replace_composition", service)
    body = {
        "characters": [{"character_id": str(cid), "is_primary": True}],
        "lorebooks": [
            {"lorebook_id": str(bid), "scope": "selected", "character_ids": [str(cid)]}
        ],
    }
    response = client.put(f"/products/{pid}/composition", json=body)
    assert response.status_code == 200
    assert response.json()["lorebooks"][0]["character_ids"] == [str(cid)]
    assert (
        client.put(
            f"/products/{pid}/composition", json={**body, "owner_id": str(uuid4())}
        ).status_code
        == 422
    )
    body["characters"][0]["persona_prompt"] = "HTTP-only injection"
    assert client.put(f"/products/{pid}/composition", json=body).status_code == 422
    assert service.await_count == 1


@pytest.mark.parametrize("operation", ["settings", "releases"])
def test_settings_and_release_adapters_pass_application_types(
    http, monkeypatch, operation
):
    _app, client, owner, _session = http
    pid, model_id, entry_id, snapshot_id = uuid4(), uuid4(), uuid4(), uuid4()
    if operation == "settings":
        body = {
            "model_id": str(model_id),
            "reasoning_effort": "low",
            "start_entry_ids": [str(entry_id)],
        }
        expected = types.ProductSettingsInfo(model_id, "low", (entry_id,))
        service = AsyncMock(return_value=expected)
        monkeypatch.setattr(settings, "set_settings", service)
        response = client.put(f"/products/{pid}/settings", json=body)
        assert response.json()["start_entry_ids"] == [str(entry_id)]
    else:
        body = {"summary": "First", "body": "Initial release"}
        expected = types.ReleaseNoteCommand("First", "Initial release")
        service = AsyncMock(
            return_value=types.ReleaseInfo(
                snapshot_id, 1, "First", "Initial release", "initial", "choice"
            )
        )
        monkeypatch.setattr(releases, "publish_product", service)
        response = client.post(f"/products/{pid}/releases", json=body)
        assert response.json()["snapshot_id"] == str(snapshot_id)
    assert response.status_code in (200, 201)
    assert service.await_args.args[1].owner_id == owner
    assert type(service.await_args.args[1].value) is type(expected)
    assert service.await_args.args[1].value == expected


def test_product_list_query_and_response_pass_through_dtos(http, monkeypatch):
    _app, client, owner, _session = http
    now, pid = datetime.now(UTC), uuid4()
    service = AsyncMock(
        return_value=[
            types.ProductInfo(pid, "Title", None, None, "private", "draft", now, now)
        ]
    )
    monkeypatch.setattr(query, "list_products", service)
    response = client.get("/products/mine", params={"offset": 2, "limit": 3})
    assert response.status_code == 200
    assert response.json()[0]["id"] == str(pid)
    assert service.await_args.args[1] == types.ListProductsCommand(
        owner_id=owner, offset=2, limit=3
    )
    assert client.get("/products/mine", params={"limit": 101}).status_code == 422
    assert service.await_count == 1


def test_typed_notices_and_statistics_keep_public_json_contract(http, monkeypatch):
    _app, client, _owner, _session = http
    pid, sid, start_id = uuid4(), uuid4(), uuid4()
    now, day = datetime.now(UTC), date(2026, 9, 9)
    notice = ModelNoticeView(state="scheduled", shutdown_at=now)
    published = types.PublishedProductView(
        pid, sid, 1, "Title", None, [types.StartOptionInfo(start_id, "Start")], notice
    )
    monkeypatch.setattr(
        notices, "get_published_product", AsyncMock(return_value=published)
    )
    response = client.get(f"/products/{pid}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["start_options"] == [{"id": str(start_id), "title": "Start"}]
    assert payload["model_notice"]["state"] == "scheduled"
    assert (
        "persona_prompt" not in response.text and "snapshot_data" not in response.text
    )

    metrics = {
        f.name: 0 for f in fields(types.StatisticsMetricsInfo) if f.name != "revenue"
    }
    revenue = {"KRW": types.RevenueInfo("100.00", "20.00", "80.00", 1, 1)}
    report = types.StatisticsInfo(
        pid,
        sid,
        "Asia/Seoul",
        day,
        day,
        types.StatisticsMetricsInfo(**metrics, revenue=revenue),
        [day],
        [types.StatisticsDayInfo(**metrics, revenue=revenue, day=day, updated_at=now)],
    )
    monkeypatch.setattr(statistics, "get_statistics", AsyncMock(return_value=report))
    response = client.get(
        f"/products/{pid}/statistics",
        params={
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "snapshot_id": str(sid),
        },
    )
    assert response.status_code == 200
    assert response.json()["totals"]["revenue"]["KRW"]["net"] == "80.00"
    assert response.json()["pending_days"] == [day.isoformat()]


@pytest.mark.parametrize("operation", ["start", "switch", "expiry"])
def test_conversation_and_admin_adapters_serialize_typed_results(
    http, monkeypatch, operation
):
    _app, client, owner, _session = http
    pid, cid, sid, start_id = uuid4(), uuid4(), uuid4(), uuid4()
    if operation == "start":
        service = AsyncMock(
            return_value=conversation_types.ConversationStartedInfo(cid, sid, start_id)
        )
        monkeypatch.setattr(conversation_service, "start_conversation", service)
        # The start router imports this function at module load.
        monkeypatch.setattr(
            "app.modules.chatting.conversation.router.start_conversation", service
        )
        response = client.post(
            "/conversations",
            json={"product_id": str(pid), "start_set_id": str(start_id)},
        )
        assert response.status_code == 201
        assert response.json() == {
            "id": str(cid),
            "product_snapshot_id": str(sid),
            "start_set_id": str(start_id),
        }
        assert service.await_args.args[1].user_id == owner
        assert service.await_args.args[1].start_set_id == start_id
    elif operation == "switch":
        service = AsyncMock(
            return_value=conversation_types.VersionSwitchedInfo(sid, True)
        )
        monkeypatch.setattr(versions, "switch_version", service)
        response = client.post(
            f"/conversations/{cid}/version", json={"target_snapshot_id": str(sid)}
        )
        assert response.status_code == 200
        assert response.json() == {"snapshot_id": str(sid), "changed": True}
        assert service.await_args.args[1].user_id == owner
    else:
        service = AsyncMock(
            return_value=admin_types.ExpiryChangedInfo(sid, None, "Policy")
        )
        monkeypatch.setattr(product_policy, "set_expiry", service)
        monkeypatch.setattr(
            "app.modules.governance.admin.product_router.set_expiry", service
        )
        response = client.put(
            f"/admin/products/versions/{sid}/expiry",
            json={"expires_at": None, "reason": "Policy"},
        )
        assert response.status_code == 200
        assert response.json() == {
            "snapshot_id": str(sid),
            "expires_at": None,
            "reason": "Policy",
        }
        assert service.await_args.args[1].actor_id == owner


def test_http_routes_use_schema_models_and_application_layers_do_not_import_them(http):
    app, _client, _owner, _session = http
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for body in route.dependant.body_params:
            assert issubclass(body.type_, BaseModel), route.path
            assert body.type_.__module__.endswith(".schemas"), route.path
        if route.status_code == 204:
            continue
        response = route.response_model
        if get_origin(response) is list:
            response = get_args(response)[0]
        assert response and issubclass(response, BaseModel), route.path
        assert response.__module__.endswith(".schemas"), route.path

    modules = Path(__file__).parents[1] / "app/modules"
    for domain in (
        "content/product",
        "chatting/conversation",
        "governance/admin",
        "llm",
    ):
        for path in (modules / domain).rglob("*.py"):
            if (
                "mapper" in path.parts
                or path.name.endswith("router.py")
                or path.name in ("dependencies.py", "http.py", "__init__.py")
            ):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                names = {n.name for n in node.names}
                if path.name == "schemas.py":
                    assert not module.endswith(".types") and "types" not in names, path
                else:
                    assert not module.endswith(".schemas") and "schemas" not in names, (
                        path
                    )
                    assert ".mapper.schema" not in module, path
                    assert not (module == "pydantic" and "BaseModel" in names), path
