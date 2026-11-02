"""Malformed editor inputs return 422 before writes; unfinished drafts remain usable."""

from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_studio_republication_contracts import Backend
from test_studio_republication_contracts import backend as backend_fixture

from app.http import studio_publication as Http
from app.http.dependencies import get_current_owner_id, get_product_session
from app.modules.content.character import types as CharacterTypes
from app.modules.content.product import types as Types
from app.modules.content.product.service.command import studio as Studio
from app.modules.content.product.service.studio_validation import (
    validate_studio_document_shape,
)
from app.use_cases import studio_components as Components
from app.use_cases import studio_publication as Publication

backend = backend_fixture


def at(
    value: Types.ProductJsonValue, path: tuple[str | int, ...]
) -> Types.ProductJsonValue:
    for key in path:
        if isinstance(key, str):
            assert isinstance(value, dict)
            value = value[key]
        else:
            assert isinstance(value, list)
            value = value[key]
    return value


def change(
    document: Types.ProductJsonObject,
    path: tuple[str | int, ...],
    value: Types.ProductJsonValue,
) -> Types.ProductJsonObject:
    result = deepcopy(document)
    parent = at(result, path[:-1])
    key = path[-1]
    if isinstance(key, str):
        assert isinstance(parent, dict)
        parent[key] = value
    else:
        assert isinstance(parent, list)
        parent[key] = value
    return result


@pytest_asyncio.fixture
async def client(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(Http.router)
    monkeypatch.setattr(
        Components,
        "get_studio_draft_for_publication",
        backend.operations["get_studio_draft_for_publication"],
    )
    async with AsyncSession() as session:
        app.dependency_overrides[get_product_session] = lambda: session
        app.dependency_overrides[get_current_owner_id] = lambda: (
            backend.command.owner_id
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            yield client


async def publish(client: AsyncClient, item: Backend) -> int:
    response = await client.post(
        f"/products/{item.command.product_id}/studio-publication",
        json={
            "expected_revision": item.command.expected_revision,
            "model_id": str(item.command.model_id),
            "reasoning_effort": item.command.reasoning_effort,
            "summary": item.command.summary,
            "body": item.command.body,
        },
    )
    assert response.status_code != 404
    return response.status_code


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["save", "publish"])
@pytest.mark.parametrize(
    "path,value",
    [
        (("work", "visibility"), []),
        (("work", "defaultSceneId"), ["scene"]),
        (("work", "defaultSceneId"), "missing-scene"),
        (("characters",), {}),
        (("characters", 0), "invalid-row"),
        (("characters", 0, "assets"), {}),
        (("characters", 0, "assets", 0), None),
        (
            ("characters", 0, "assets", 0),
            {"usage": "expression", "mediaId": "00000000-0000-0000-0000-000000000001"},
        ),
        (("characters", 0, "assets", 0, "usage"), 3),
        (("characters", 0, "assets", 0, "usage"), "unknown"),
        (("characters", 0, "assets", 0, "id"), ""),
        (("characters", 0, "assets", 0, "mediaId"), ["invalid"]),
        (("characters", 0, "assets", 0, "mediaId"), "not-a-uuid"),
        (("scenes", 0, "characterId"), []),
        (("scenes", 0, "characterId"), "missing-character"),
        (("lorebooks", 0, "category"), {}),
        (("lorebooks", 0, "priority"), []),
        (("lorebooks", 0, "enabled"), 1),
        (("lorebooks", 0, "tokenBudget"), True),
        (("scenes", 0, "background"), 7),
    ],
)
async def test_malformed_nested_document_is_422_without_domain_writes(
    backend: Backend,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    path: tuple[str | int, ...],
    value: Types.ProductJsonValue,
) -> None:
    document = change(
        backend.draft.document,
        ("characters", 0, "assets"),
        [{"id": "image", "usage": "expression", "mediaId": str(uuid4())}],
    )
    document = change(document, path, value)
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    save = AsyncMock()
    monkeypatch.setattr(Studio, "save_studio_draft", save)
    if operation == "save":
        response = await client.put(
            f"/products/{backend.command.product_id}/studio-draft",
            json={"expected_revision": 2, "document": document},
        )
        assert response.status_code == 422
    else:
        assert await publish(client, backend) == 422
    save.assert_not_awaited()
    for name, mocked in backend.operations.items():
        if name != "get_studio_draft_for_publication":
            mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_unfinished_draft_and_extension_keys_are_saved_without_coercion(
    backend: Backend,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document: Types.ProductJsonObject = {
        "version": 2,
        "work": {
            "title": "Draft",
            "introduction": "",
            "visibility": "비공개",
            "defaultSceneId": "",
            "worldRules": "",
        },
        "characters": [
            {
                "id": "hero",
                "name": "",
                "persona": "",
                "assets": [{"id": "pending-image", "usage": "portrait"}],
            }
        ],
        "lorebooks": [{"id": "world", "title": "", "content": ""}],
        "scenes": [],
        "extension": {"nested": [None, True, "원문"]},
    }
    original = deepcopy(document)
    save = AsyncMock(return_value=replace(backend.draft, document=document, revision=3))
    monkeypatch.setattr(Studio, "save_studio_draft", save)
    response = await client.put(
        f"/products/{backend.command.product_id}/studio-draft",
        json={"expected_revision": 2, "document": document},
    )
    assert response.status_code == 200
    assert response.json()["document"] == document == original
    call = save.await_args
    assert call is not None and call.args[1].document == document
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    assert await publish(client, backend) == 422
    backend.operations["update_character"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("tokenBudget", -1), ("scanDepth", 0), ("activation", "invalid")]
)
async def test_invalid_lore_options_fail_before_character_or_book_writes(
    backend: Backend,
    client: AsyncClient,
    field: str,
    value: Types.ProductJsonValue,
) -> None:
    document = change(backend.draft.document, ("lorebooks", 0, field), value)
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    assert await publish(client, backend) == 422
    backend.operations["update_character"].assert_not_awaited()
    backend.operations["update_lorebook"].assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_preparation_checks_all_characters_before_creating_any(
    backend: Backend,
    client: AsyncClient,
) -> None:
    document = change(
        backend.draft.document,
        ("characters",),
        [
            {"id": "new", "name": "Valid", "persona": "Text"},
            {"id": "other", "name": "Incomplete"},
        ],
    )
    document = change(document, ("scenes",), [])
    document = change(document, ("work", "defaultSceneId"), "")
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    response = await client.post(
        f"/products/{backend.command.product_id}/studio-components",
        json={"expected_revision": 2},
    )
    assert response.status_code == 422
    backend.operations["create_character"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("category", [[], {}])
async def test_unsaved_diagnostics_returns_422_for_unhashable_category(
    client: AsyncClient,
    category: Types.ProductJsonValue,
) -> None:
    response = await client.post(
        "/products/studio/lore-diagnostics",
        json={
            "entries": [
                {
                    "id": "lore",
                    "title": "Title",
                    "content": "Text",
                    "category": category,
                }
            ]
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("section", ["characters", "lorebooks", "scenes"])
def test_duplicate_local_ids_are_rejected(backend: Backend, section: str) -> None:
    document = deepcopy(backend.draft.document)
    rows = document[section]
    assert isinstance(rows, list)
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match="distinct"):
        validate_studio_document_shape(document)


@pytest.mark.asyncio
async def test_direct_draft_service_rejects_shape_before_repository_access(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = AsyncMock()
    monkeypatch.setattr(Studio.Repository, "get_product_for_update", read)
    invalid = change(backend.draft.document, ("work", "visibility"), [])
    async with AsyncSession() as session:
        with pytest.raises(ValueError, match="visibility"):
            await Studio.save_studio_draft(
                session,
                Types.SaveStudioDraftCommand(
                    backend.command.product_id,
                    backend.command.owner_id,
                    2,
                    invalid,
                ),
            )
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_image_is_draft_valid_but_publication_requires_upload(
    backend: Backend,
    client: AsyncClient,
) -> None:
    document = change(
        backend.draft.document,
        ("characters", 0, "assets"),
        [{"id": "image", "usage": "portrait"}],
    )
    validate_studio_document_shape(document)
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    assert await publish(client, backend) == 422
    backend.operations["update_character"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_usage", [False, True])
async def test_valid_uploaded_image_keeps_legacy_usage_default_and_owner_command(
    backend: Backend,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    explicit_usage: bool,
) -> None:
    media_id = uuid4()
    asset: Types.ProductJsonObject = {"id": "image", "mediaId": str(media_id)}
    if explicit_usage:
        asset["usage"] = "portrait"
    document = change(backend.draft.document, ("characters", 0, "assets"), [asset])
    backend.operations["get_studio_draft_for_publication"].return_value = replace(
        backend.draft, document=document
    )
    attach = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(Publication.CharacterCommand, "add_character_asset", attach)
    assert await publish(client, backend) == 200
    call = attach.await_args
    assert call is not None
    command: CharacterTypes.CreateCharacterAssetCommand = call.args[1]
    assert command.owner_id == backend.command.owner_id
    assert command.character_id == backend.character_id
    assert command.purpose == (
        "studio:image:portrait" if explicit_usage else "studio:image:expression"
    )
    assert command.file_url == f"/characters/media/{media_id}/content"


@pytest.mark.asyncio
async def test_receipt_replay_precedes_validation_of_a_newer_legacy_document(
    backend: Backend,
    client: AsyncClient,
) -> None:
    assert await publish(client, backend) == 200
    call = backend.operations["mark_studio_publication"].await_args
    assert call is not None
    mapping = call.args[1].mapping
    newer = replace(
        backend.draft,
        revision=3,
        document={"work": []},
        publication_release={"_studio": mapping},
    )
    for operation in backend.operations.values():
        operation.reset_mock()
    backend.operations["get_studio_draft_for_publication"].return_value = newer
    assert await publish(client, backend) == 200
    for name, operation in backend.operations.items():
        if name != "get_studio_draft_for_publication":
            operation.assert_not_awaited()
