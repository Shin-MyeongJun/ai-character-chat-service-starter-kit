"""Offline studio JSON boundary compatibility and HTTP response contracts."""

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from typing import TypeAlias
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import studio_publication as Http
from app.http.dependencies import get_current_owner_id, get_product_session
from app.modules.content.product import types as ProductTypes
from app.use_cases import studio_components as Components

HttpContext: TypeAlias = tuple[FastAPI, TestClient, UUID, object]


@pytest.fixture
def http() -> Iterator[HttpContext]:
    app = FastAPI()
    app.include_router(Http.router)
    owner_id = uuid4()
    session = object()
    app.dependency_overrides[get_current_owner_id] = lambda: owner_id
    app.dependency_overrides[get_product_session] = lambda: session
    with TestClient(app) as client:
        yield app, client, owner_id, session


def test_unsaved_lore_uses_real_domain_diagnostics_and_keeps_empty_response_schema(
    http: HttpContext,
) -> None:
    app, client, _owner_id, _session = http
    response = client.post(
        "/products/studio/lore-diagnostics",
        json={
            "entries": [
                {
                    "id": "local-lore",
                    "title": "세계",
                    "content": "한국어 원문 🌏",
                    "activation": "always",
                    "extension": {"nested": [None, True, 3]},
                }
            ],
            "messages": [],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["active_ids"] == ["local-lore"]
    assert result["ai_called"] is False
    assert result["items"][0]["id"] == "local-lore"
    assert result["items"][0]["included"] is True
    paths = app.openapi()["paths"]
    for path in (
        "/products/studio/lore-diagnostics",
        "/products/{product_id}/studio-components",
    ):
        assert (
            paths[path]["post"]["responses"]["200"]["content"]["application/json"][
                "schema"
            ]
            == {}
        )


@pytest.mark.parametrize(
    "change",
    [
        {"id": 123},
        {"keywords": "not-a-list"},
        {"enabled": 1},
        {"tokenBudget": True},
        {"activation": "unknown"},
    ],
)
def test_unsaved_lore_rejects_invalid_values_at_existing_validation_boundaries(
    http: HttpContext, change: dict[str, object]
) -> None:
    _app, client, _owner_id, _session = http
    response = client.post(
        "/products/studio/lore-diagnostics",
        json={
            "entries": [{"id": "local", "title": "Title", "content": "Text", **change}],
            "messages": [],
        },
    )
    assert response.status_code == 422


def test_preparation_keeps_trusted_actor_and_unfiltered_response(
    http: HttpContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    _app, client, owner_id, session = http
    product_id, character_id = uuid4(), uuid4()
    result = {
        "characters": {"local-hero": str(character_id)},
        "extension": {"unchanged": [None, True]},
    }
    prepare = AsyncMock(return_value=result)
    monkeypatch.setattr(Http, "prepare_components", prepare)
    response = client.post(
        f"/products/{product_id}/studio-components", json={"expected_revision": 3}
    )
    assert response.status_code == 200
    assert response.json() == result
    assert prepare.await_args is not None
    assert prepare.await_args.args == (
        session,
        ProductTypes.GetStudioDraftCommand(product_id, owner_id),
        3,
    )
    prepare.side_effect = ProductTypes.StudioDraftConflictError("changed")
    response = client.post(
        f"/products/{product_id}/studio-components", json={"expected_revision": 3}
    )
    assert response.status_code == 409 and response.json() == {"detail": "changed"}


@pytest.mark.asyncio
async def test_existing_component_mapping_is_deeply_detached_with_extensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapping: ProductTypes.ProductJsonObject = {
        "characters": {"local": str(uuid4())},
        "entries": {},
        "receipts": {},
        "extension": {"nested": ["original"]},
    }
    original = deepcopy(mapping)
    draft = ProductTypes.StudioDraftInfo(
        product_id=uuid4(),
        revision=2,
        document={},
        updated_at=datetime.now(UTC),
        publication_release={"_studio": mapping},
    )
    get_composition = AsyncMock()
    monkeypatch.setattr(Components, "get_composition", get_composition)
    async with AsyncSession() as session:
        copied = await Components.component_mapping(session, draft, uuid4())
    assert copied == original and copied is not mapping
    copied["characters"]["local"] = str(uuid4())
    copied_extension = copied.get("extension")
    assert isinstance(copied_extension, dict)
    copied_extension["nested"].append("changed")
    assert mapping == original
    get_composition.assert_not_awaited()
