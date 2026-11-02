"""Conversation HTTP contracts, trusted dependencies and unchanged nullable failure."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.http import dependencies
from app.modules.chatting.conversation import router as Router
from app.modules.chatting.conversation import types
from app.modules.chatting.conversation.service.command import (
    versions as VersionsService,
)
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.views import notices as NoticesService


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(Router.router)
    session, owner_id = object(), uuid4()
    app.dependency_overrides[dependencies.get_product_session] = lambda: session
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner_id
    with TestClient(app) as client:
        yield client, app, session, owner_id


def test_start_keeps_201_response_and_builds_command_with_trusted_owner(
    api, monkeypatch
):
    client, _app, session, owner_id = api
    product_id, conversation_id, snapshot_id, start_id = [uuid4() for _ in range(4)]
    service = AsyncMock(
        return_value=types.ConversationStartedInfo(
            conversation_id, snapshot_id, start_id
        )
    )
    monkeypatch.setattr(Router, "start_conversation", service)
    response = client.post(
        "/conversations",
        json={"product_id": str(product_id), "start_set_id": str(start_id)},
    )
    assert response.status_code == 201
    assert response.json() == {
        "id": str(conversation_id),
        "product_snapshot_id": str(snapshot_id),
        "start_set_id": str(start_id),
    }
    service.assert_awaited_once_with(
        session,
        types.StartConversationCommand(
            product_id=product_id, user_id=owner_id, start_set_id=start_id
        ),
    )


def test_switch_keeps_idempotent_false_and_uses_path_owner_and_body_ids(
    api, monkeypatch
):
    client, _app, session, owner_id = api
    conversation_id, target_id = uuid4(), uuid4()
    service = AsyncMock(return_value=types.VersionSwitchedInfo(target_id, False))
    monkeypatch.setattr(VersionsService, "switch_version", service)
    response = client.post(
        f"/conversations/{conversation_id}/version",
        json={"target_snapshot_id": str(target_id)},
    )
    assert response.status_code == 200 and response.json() == {
        "snapshot_id": str(target_id),
        "changed": False,
    }
    service.assert_awaited_once_with(
        session,
        types.SwitchVersionCommand(
            conversation_id=conversation_id,
            user_id=owner_id,
            target_snapshot_id=target_id,
        ),
    )


def test_updates_keep_expiry_note_fields_and_trusted_conversation_scope(
    api, monkeypatch
):
    client, _app, session, owner_id = api
    conversation_id, current_id, latest_id = uuid4(), uuid4(), uuid4()
    result = ProductTypes.PendingUpdatesView(
        current_id,
        None,
        None,
        latest_id,
        [
            ProductTypes.UpdateInfo(
                latest_id, 2, "Next", "Body", "content", "choice", None
            )
        ],
        None,
    )
    service = AsyncMock(return_value=result)
    monkeypatch.setattr(NoticesService, "get_pending_updates", service)
    response = client.get(f"/conversations/{conversation_id}/updates")
    assert response.status_code == 200
    assert response.json() == {
        "current_snapshot_id": str(current_id),
        "current_expires_at": None,
        "expiry_reason": None,
        "latest_snapshot_id": str(latest_id),
        "model_notice": None,
        "updates": [
            {
                "snapshot_id": str(latest_id),
                "version": 2,
                "summary": "Next",
                "body": "Body",
                "change_kind": "content",
                "update_policy": "choice",
                "expires_at": None,
            }
        ],
    }
    service.assert_awaited_once_with(
        session,
        ProductTypes.PendingUpdatesCommand(
            conversation_id=conversation_id, user_id=owner_id
        ),
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_start_view_preserves_fixed_and_legacy_null_fields(api, monkeypatch, legacy):
    client, _app, session, owner_id = api
    conversation_id, snapshot_id, slot_id = uuid4(), uuid4(), uuid4()
    result = types.ConversationStartView(
        None if legacy else snapshot_id,
        "legacy_messages" if legacy else "snapshot",
        None if legacy else "Opening",
        None if legacy else types.RuntimeStart("Title", "Scene"),
        (types.ConversationCharacterInfo(None, None if legacy else slot_id, 0),),
        None if legacy else slot_id,
    )
    service = AsyncMock(return_value=result)
    monkeypatch.setattr(Router.ViewsService, "get_conversation_start", service)
    response = client.get(f"/conversations/{conversation_id}/start")
    assert response.status_code == 200
    assert response.json() == {
        "initial_snapshot_id": None if legacy else str(snapshot_id),
        "opening_mode": "legacy_messages" if legacy else "snapshot",
        "opening_message": None if legacy else "Opening",
        "start": None if legacy else {"title": "Title", "content": "Scene"},
        "participants": [
            {
                "character_id": None,
                "product_character_id": None if legacy else str(slot_id),
                "role_order": 0,
            }
        ],
        "primary_product_character_id": None if legacy else str(slot_id),
    }
    service.assert_awaited_once_with(
        session,
        types.OwnedConversationCommand(
            conversation_id=conversation_id, user_id=owner_id
        ),
    )


def test_manual_lore_keeps_raw_items_response_and_empty_openapi_schema(
    api, monkeypatch
):
    client, app, session, owner_id = api
    conversation_id = uuid4()
    service = AsyncMock(return_value=(types.ManualLoreInfo("entry", "Manual"),))
    monkeypatch.setattr(Router.ViewsService, "list_manual_lore", service)
    response = client.get(f"/conversations/{conversation_id}/manual-lore")
    assert response.status_code == 200 and response.json() == {
        "items": [{"id": "entry", "title": "Manual"}]
    }
    service.assert_awaited_once_with(
        session,
        types.OwnedConversationCommand(
            conversation_id=conversation_id, user_id=owner_id
        ),
    )
    schema = app.openapi()["paths"]["/conversations/{conversation_id}/manual-lore"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {}


@pytest.mark.parametrize(
    ("error", "status"),
    [(LookupError("Missing conversation"), 404), (ValueError("Invalid version"), 422)],
)
def test_service_errors_keep_404_and_422_translation(api, monkeypatch, error, status):
    client, _app, _session, _owner_id = api
    monkeypatch.setattr(
        Router.ViewsService, "get_conversation_start", AsyncMock(side_effect=error)
    )
    response = client.get(f"/conversations/{uuid4()}/start")
    assert response.status_code == status and response.json() == {"detail": str(error)}


@pytest.mark.parametrize("missing", ["session", "owner"])
def test_unconfigured_dependency_blocks_service_call(api, monkeypatch, missing):
    client, app, _session, _owner_id = api
    dependency = (
        dependencies.get_product_session
        if missing == "session"
        else dependencies.get_current_owner_id
    )
    app.dependency_overrides.pop(dependency)
    service = AsyncMock()
    monkeypatch.setattr(Router.ViewsService, "get_conversation_start", service)
    response = client.get(f"/conversations/{uuid4()}/start")
    assert response.status_code == 503
    service.assert_not_awaited()


def test_start_body_cannot_supply_a_user_id(api, monkeypatch):
    client, _app, _session, _owner_id = api
    service = AsyncMock()
    monkeypatch.setattr(Router, "start_conversation", service)
    response = client.post(
        "/conversations", json={"product_id": str(uuid4()), "user_id": str(uuid4())}
    )
    assert response.status_code == 422
    service.assert_not_awaited()


def test_nullable_start_title_keeps_existing_http_validation_failure(api, monkeypatch):
    client, _app, _session, _owner_id = api
    result = types.ConversationStartView(
        uuid4(), "snapshot", "Opening", types.RuntimeStart(None, "Scene"), (), None
    )
    monkeypatch.setattr(
        Router.ViewsService, "get_conversation_start", AsyncMock(return_value=result)
    )
    response = client.get(f"/conversations/{uuid4()}/start")
    assert response.status_code == 422
    assert "start.title" in response.json()["detail"]
