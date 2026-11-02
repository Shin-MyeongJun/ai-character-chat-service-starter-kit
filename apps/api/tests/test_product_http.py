"""Product HTTP responses, trusted owners and typed query/body conversion."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.http import dependencies, studio_publication
from app.modules.content.product import router as Router
from app.modules.content.product import schemas, types
from app.modules.content.product.service import tags as TagsService
from app.modules.content.tag import types as TagTypes


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(Router.router)
    session, owner_id = object(), uuid4()
    app.dependency_overrides[dependencies.get_product_session] = lambda: session
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: owner_id
    with TestClient(app) as client:
        yield client, app, session, owner_id


def product_info(product_id):
    now = datetime(2026, 10, 28, tzinfo=UTC)
    return types.ProductInfo(
        id=product_id,
        title="Title",
        description=None,
        opening_message=None,
        visibility="private",
        status="draft",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.parametrize(
    ("method", "operation"),
    [
        ("GET", "list_public_tags"),
        ("POST", "add_public_tags"),
        ("PUT", "replace_public_tags"),
        ("DELETE", "remove_public_tag"),
    ],
)
def test_tag_routes_use_trusted_owner_keep_dtos_and_empty_delete(
    api, monkeypatch, method, operation
):
    client, app, session, owner_id = api
    target_id, tag_id = uuid4(), uuid4()
    info = TagTypes.PublicTagInfo(tag_id, "Fantasy", False, 3)
    service = AsyncMock(return_value=None if method == "DELETE" else (info,))
    monkeypatch.setattr(TagsService, operation, service)
    path = f"/products/{target_id}/tags"
    if method == "DELETE":
        path += f"/{tag_id}"
    response = client.request(
        method,
        path,
        json={"tags": ["Fantasy"]} if method in ("POST", "PUT") else None,
    )
    if method == "DELETE":
        assert response.status_code == 204 and response.content == b""
        operation_schema = app.openapi()["paths"][
            "/products/{target_id}/tags/{tag_id}"
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


def test_catalog_keeps_cursor_filters_and_raw_tag_response_without_owner(
    api, monkeypatch
):
    client, app, session, _owner_id = api
    app.dependency_overrides.pop(dependencies.get_current_owner_id)
    product_id, snapshot_id, tag_id = uuid4(), uuid4(), uuid4()
    stamp = datetime(2026, 10, 28, tzinfo=UTC)
    service = AsyncMock(
        return_value=types.CatalogPageInfo(
            (
                types.CatalogProductInfo(
                    product_id, "Published", None, snapshot_id, stamp
                ),
            ),
            stamp,
            product_id,
        )
    )
    tags = AsyncMock(
        return_value=(TagTypes.TagInfo(tag_id, "Fantasy", "hidden", True),)
    )
    monkeypatch.setattr(Router.QueryService, "list_catalog", service)
    monkeypatch.setattr(Router.QueryService, "list_catalog_tags", tags)
    response = client.get(
        "/products/catalog",
        params={
            "limit": 1,
            "cursor_created_at": stamp.isoformat(),
            "cursor_id": str(product_id),
            "search": "100%_",
            "tag_id": str(tag_id),
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["snapshot_id"] == str(snapshot_id)
    assert response.json()["next_cursor_id"] == str(product_id)
    service.assert_awaited_once_with(
        session,
        types.ListCatalogCommand(
            limit=1,
            cursor_created_at=stamp,
            cursor_id=product_id,
            search="100%_",
            tag_id=tag_id,
        ),
    )
    assert client.get("/products/catalog-tags").json() == [
        {"id": str(tag_id), "name": "Fantasy"}
    ]
    tags.assert_awaited_once_with(session)
    assert (
        app.openapi()["paths"]["/products/catalog-tags"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == {}
    )
    invalid = client.get("/products/catalog", params={"cursor_created_at": "invalid"})
    assert invalid.status_code == 422 and service.await_count == 1


def test_owner_list_and_count_keep_array_and_exact_total_shapes(api, monkeypatch):
    client, app, session, owner_id = api
    info = product_info(uuid4())
    listing = AsyncMock(return_value=[info])
    counting = AsyncMock(return_value=123)
    monkeypatch.setattr(Router.QueryService, "list_products", listing)
    monkeypatch.setattr(Router.QueryService, "count_products", counting)
    response = client.get(
        "/products/mine", params={"offset": 4, "limit": 2, "search": "  title  "}
    )
    assert response.status_code == 200 and response.json()[0]["id"] == str(info.id)
    listing.assert_awaited_once_with(
        session,
        types.ListProductsCommand(
            owner_id=owner_id,
            offset=4,
            limit=2,
            search="title",
        ),
    )
    count = client.get("/products/mine/count", params={"search": "title"})
    assert count.status_code == 200 and count.json() == {"total": 123}
    counting.assert_awaited_once_with(
        session, types.ListProductsCommand(owner_id=owner_id, search="title")
    )
    assert (
        app.openapi()["paths"]["/products/mine/count"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        == {}
    )


@pytest.mark.parametrize(
    ("fields", "tags"),
    [
        ({}, None),
        ({"tags": None}, None),
        ({"tags": []}, ()),
        ({"tags": ["Fantasy"]}, ("Fantasy",)),
    ],
)
def test_update_preserves_omitted_null_and_clear_tags(api, monkeypatch, fields, tags):
    client, _app, session, owner_id = api
    product_id = uuid4()
    service = AsyncMock(return_value=product_info(product_id))
    monkeypatch.setattr(Router.CommandService, "update_product", service)
    response = client.put(
        f"/products/{product_id}/draft", json={"title": "  Title  ", **fields}
    )
    assert response.status_code == 200
    service.assert_awaited_once_with(
        session,
        types.UpdateProductCommand(
            product_id=product_id,
            owner_id=owner_id,
            value=types.ProductProfileCommand(title="Title"),
            tags=tags,
        ),
    )


def test_product_delete_keeps_204_and_trusted_owner(api, monkeypatch):
    client, app, session, owner_id = api
    product_id = uuid4()
    service = AsyncMock()
    monkeypatch.setattr(Router.CommandService, "delete_product", service)
    response = client.delete(f"/products/{product_id}/draft")
    assert response.status_code == 204 and response.content == b""
    service.assert_awaited_once_with(
        session, types.DeleteProductCommand(product_id=product_id, owner_id=owner_id)
    )
    assert (
        "content"
        not in app.openapi()["paths"]["/products/{product_id}/draft"]["delete"][
            "responses"
        ]["204"]
    )


@pytest.mark.parametrize("auto_apply", [False, True])
def test_note_correction_keeps_policy_guard_and_ids(api, monkeypatch, auto_apply):
    client, _app, session, owner_id = api
    product_id, snapshot_id = uuid4(), uuid4()
    service = AsyncMock(
        return_value=types.ReleaseInfo(
            snapshot_id, 2, "Summary", "Body", "content", "choice"
        )
    )
    monkeypatch.setattr(Router.ReleasesCommandService, "correct_note", service)
    response = client.patch(
        f"/products/{product_id}/releases/{snapshot_id}/note",
        json={
            "summary": " Summary ",
            "body": " Body ",
            "auto_apply_media": auto_apply,
        },
    )
    if auto_apply:
        assert response.status_code == 422
        service.assert_not_awaited()
    else:
        assert response.status_code == 200 and response.json()["snapshot_id"] == str(
            snapshot_id
        )
        service.assert_awaited_once_with(
            session,
            types.CorrectNoteCommand(
                product_id=product_id,
                snapshot_id=snapshot_id,
                owner_id=owner_id,
                summary="Summary",
                body="Body",
            ),
        )


def test_studio_response_keeps_nested_json_and_hides_receipt_fields(api, monkeypatch):
    client, _app, session, owner_id = api
    product_id = uuid4()
    document = {"extension": [True, 0, None, {"text": "  raw  "}], "version": 1}
    service = AsyncMock(
        return_value=types.StudioDraftInfo(
            product_id=product_id,
            revision=2,
            document=document,
            updated_at=datetime(2026, 10, 28, tzinfo=UTC),
            content_digest="secret",
            publication_digest="receipt",
            publication_release={"hidden": True},
        )
    )
    monkeypatch.setattr(Router, "get_studio_draft", service)
    response = client.get(f"/products/{product_id}/studio-draft")
    assert response.status_code == 200 and response.json()["document"] == document
    assert set(response.json()) == {"product_id", "revision", "document", "updated_at"}
    service.assert_awaited_once_with(
        session, types.GetStudioDraftCommand(product_id=product_id, owner_id=owner_id)
    )
    assert (
        schemas.SaveStudioDraftRequestDto.model_validate(
            {"document": document}
        ).document
        == document
    )


def test_studio_save_keeps_json_values_and_uses_trusted_ids(api, monkeypatch):
    client, app, session, owner_id = api
    app.include_router(studio_publication.router)
    product_id = uuid4()
    document = {"extension": [True, 0, 1.25, None, {"text": "  raw  "}], "version": 1}
    service = AsyncMock(
        return_value=types.StudioDraftInfo(
            product_id=product_id,
            revision=3,
            document=document,
            updated_at=datetime(2026, 10, 28, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(studio_publication, "save_studio", service)
    response = client.put(
        f"/products/{product_id}/studio-draft",
        json={
            "expected_revision": 2,
            "document": document,
        },
    )
    assert response.status_code == 200 and response.json()["document"] == document
    service.assert_awaited_once_with(
        session,
        types.SaveStudioDraftCommand(
            product_id=product_id,
            owner_id=owner_id,
            expected_revision=2,
            document=document,
        ),
    )


def test_statistics_query_passes_dates_and_version_and_keeps_exact_currency_strings(
    api, monkeypatch
):
    from app.modules.content.product.service import statistics as StatisticsService

    client, _app, session, owner_id = api
    product_id, snapshot_id = uuid4(), uuid4()
    day = date(2026, 10, 28)
    totals = types.StatisticsMetricsInfo(
        active_users=2,
        succeeded=1,
        failed=0,
        cancelled=0,
        stale=0,
        messages=3,
        conversations=1,
        transitions=0,
        input_tokens=10,
        output_tokens=4,
        cost_credit=2,
        revenue={"USD": types.RevenueInfo("0.1000", "0.05", "0.0500", 1, 1)},
    )
    service = AsyncMock(
        return_value=types.StatisticsInfo(
            product_id, snapshot_id, "Asia/Seoul", day, day, totals, [day], []
        )
    )
    monkeypatch.setattr(StatisticsService, "get_statistics", service)
    response = client.get(
        f"/products/{product_id}/statistics",
        params={
            "date_from": str(day),
            "date_to": str(day),
            "snapshot_id": str(snapshot_id),
        },
    )
    assert response.status_code == 200
    assert response.json()["totals"]["revenue"]["USD"]["sales"] == "0.1000"
    assert (
        response.json()["pending_days"] == [str(day)] and response.json()["days"] == []
    )
    service.assert_awaited_once_with(
        session,
        types.GetStatisticsCommand(
            product_id=product_id,
            owner_id=owner_id,
            date_from=day,
            date_to=day,
            snapshot_id=snapshot_id,
        ),
    )


@pytest.mark.parametrize(
    ("error", "status"), [(LookupError("Missing"), 404), (ValueError("Invalid"), 422)]
)
def test_service_errors_keep_http_translation(api, monkeypatch, error, status):
    client, _app, _session, _owner_id = api
    monkeypatch.setattr(TagsService, "add_public_tags", AsyncMock(side_effect=error))
    response = client.post(f"/products/{uuid4()}/tags", json={"tags": ["Fantasy"]})
    assert response.status_code == status and response.json() == {"detail": str(error)}


@pytest.mark.parametrize("missing_dependency", ["session", "owner"])
def test_unconfigured_dependency_blocks_service_call(
    api, monkeypatch, missing_dependency
):
    client, app, _session, _owner_id = api
    dependency = (
        dependencies.get_product_session
        if missing_dependency == "session"
        else dependencies.get_current_owner_id
    )
    app.dependency_overrides.pop(dependency)
    service = AsyncMock()
    monkeypatch.setattr(Router.QueryService, "get_product", service)
    response = client.get(f"/products/{uuid4()}/draft")
    assert response.status_code == 503
    service.assert_not_awaited()
