"""Public catalog uses the published snapshot rather than editable draft fields."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.http import public_catalog
from app.http.dependencies import get_product_session
from app.modules.content.product.mapper.persistence import catalog_entities_to_page_info


def test_catalog_title_and_description_come_from_published_snapshot():
    product_id, snapshot_id = uuid4(), uuid4()
    created_at = datetime.now(UTC)
    product = SimpleNamespace(
        id=product_id, title="Unpublished edit", description="Not published", created_at=created_at,
    )
    snapshot = SimpleNamespace(
        id=snapshot_id, snapshot_data={"title": "Published", "description": "Visible"},
    )
    page = catalog_entities_to_page_info([(product, snapshot)], 1)
    assert page.items[0].title == "Published"
    assert page.items[0].description == "Visible"
    assert page.items[0].snapshot_id == snapshot_id
    assert page.next_cursor_id is None


@pytest.mark.asyncio
async def test_public_catalog_detail_returns_not_found_for_inaccessible_product(monkeypatch):
    product_id = uuid4()
    session = object()

    async def get_session():
        return session

    async def get_product(actual_session, command):
        assert actual_session is session
        assert command.product_id == product_id
        assert command.user_id is None
        raise LookupError("Product not found.")

    monkeypatch.setattr(public_catalog, "get_published_product", get_product)
    app = FastAPI()
    app.include_router(public_catalog.router)
    app.dependency_overrides[get_product_session] = get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/products/catalog/{product_id}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found."}
