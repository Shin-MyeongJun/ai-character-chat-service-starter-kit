"""Lorebook tag responses, trusted dependencies and HTTP error contracts."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.content.lorebook import dependencies, types
from app.modules.content.lorebook.router import router
from app.modules.content.lorebook.service import tags as TagsService
from app.modules.content.tag import types as TagTypes


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("GET", "list_public_tags"),
        ("POST", "add_public_tags"),
        ("PUT", "replace_public_tags"),
        ("DELETE", "remove_public_tag"),
    ],
)
def test_tag_routes_preserve_responses_and_use_dependency_owner(
    monkeypatch: pytest.MonkeyPatch, method: str, operation: str
) -> None:
    owner_id, target_id, tag_id = uuid4(), uuid4(), uuid4()
    session = object()
    info = TagTypes.PublicTagInfo(tag_id, "Fantasy", False, 3)
    service = AsyncMock(return_value=None if method == "DELETE" else (info,))
    monkeypatch.setattr(TagsService, operation, service)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependencies.get_lorebook_session] = lambda: session
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner_id
    path = f"/lorebooks/me/{target_id}/tags"
    if method == "DELETE":
        path += f"/{tag_id}"
    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            json={"tags": ["Fantasy"]} if method in ("POST", "PUT") else None,
        )
    if method == "DELETE":
        assert response.status_code == 204
        assert response.content == b""
        operation_schema = app.openapi()["paths"][
            "/lorebooks/me/{target_id}/tags/{tag_id}"
        ]["delete"]
        assert "content" not in operation_schema["responses"]["204"]
    else:
        assert response.status_code == 200
        assert response.json() == [
            {"id": str(tag_id), "name": "Fantasy", "is_active": False, "sort_order": 3}
        ]
    service.assert_awaited_once_with(
        session,
        types.PublicTagsCommand(
            target_id=target_id,
            user_id=owner_id,
            names=("Fantasy",) if method in ("POST", "PUT") else (),
            tag_id=tag_id if method == "DELETE" else None,
        ),
    )


@pytest.mark.parametrize(
    ("error", "status_code"),
    [(LookupError("Missing target"), 404), (ValueError("Invalid tags"), 422)],
)
def test_tag_service_errors_keep_http_translation(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int
) -> None:
    service = AsyncMock(side_effect=error)
    monkeypatch.setattr(TagsService, "add_public_tags", service)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependencies.get_lorebook_session] = lambda: object()
    app.dependency_overrides[dependencies.get_current_owner_id] = uuid4
    with TestClient(app) as client:
        response = client.post(
            f"/lorebooks/me/{uuid4()}/tags", json={"tags": ["Fantasy"]}
        )
    assert response.status_code == status_code
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize("missing_dependency", ["session", "owner"])
def test_unconfigured_lorebook_dependency_prevents_tag_service_call(
    monkeypatch: pytest.MonkeyPatch, missing_dependency: str
) -> None:
    service = AsyncMock()
    monkeypatch.setattr(TagsService, "list_public_tags", service)
    app = FastAPI()
    app.include_router(router)
    if missing_dependency == "session":
        app.dependency_overrides[dependencies.get_current_owner_id] = uuid4
    else:
        app.dependency_overrides[dependencies.get_lorebook_session] = lambda: object()
    with TestClient(app) as client:
        response = client.get(f"/lorebooks/me/{uuid4()}/tags")
    assert response.status_code == 503
    service.assert_not_awaited()
