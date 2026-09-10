from uuid import uuid4

import pytest
from app.http.dependencies import get_current_owner_id, get_product_session
from app.modules.chatting.chat.router import router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_usage import scenario


def test_message_routes_fail_closed_with_existing_unconfigured_dependencies():
    app = FastAPI()
    app.include_router(router)
    base = f"/conversations/{uuid4()}/messages"
    with TestClient(app) as client:
        assert client.get(base).status_code == 503
        assert (
            client.post(base, json={"request_key": "a", "content": "Hello"}).status_code
            == 503
        )
        assert (
            client.put(
                f"{base}/{uuid4()}", json={"content": "Edit", "expected_revision": 1}
            ).status_code
            == 503
        )
        assert client.delete(f"{base}/{uuid4()}").status_code == 503


@pytest.mark.asyncio
async def test_crud_http_contract_uses_existing_auth_and_session_hooks(db):
    owner, _product, _release, cid, _character = await scenario(db)
    app = FastAPI()
    app.include_router(router)

    async def session_dependency():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_product_session] = session_dependency
    app.dependency_overrides[get_current_owner_id] = lambda: owner.id
    base = f"/conversations/{cid}/messages"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for field, value in (
            ("sender_type", "character"),
            ("generated_by_ai", True),
            ("generation_id", str(uuid4())),
            ("product_character_id", str(uuid4())),
            ("user_id", str(uuid4())),
        ):
            response = await client.post(
                base, json={"request_key": "forged", "content": "Text", field: value}
            )
            assert response.status_code == 422
        result = await client.post(
            base, json={"request_key": "one", "content": "Hello"}
        )
        assert result.status_code == 201
        message = result.json()
        assert message["sender_type"] == "user" and message["generated_by_ai"] is False
        mid = message["id"]
        page = await client.get(base, params={"limit": 1})
        assert page.status_code == 200
        opening = page.json()["items"][0]
        cursor = page.json()["next_cursor"]
        page2 = await client.get(base, params={"cursor": cursor, "limit": 1})
        assert (
            page2.json()["items"][0]["id"] == mid
            and page2.json()["next_cursor"] is None
        )
        assert (await client.get(base, params={"cursor": "garbage"})).status_code == 422
        response = await client.put(
            f"{base}/{opening['id']}",
            json={"content": "Forged", "expected_revision": 1},
        )
        assert response.status_code == 403
        response = await client.put(
            f"{base}/{mid}", json={"content": "Changed", "expected_revision": 1}
        )
        assert response.status_code == 200 and response.json()["revision"] == 2
        assert response.json()["content"] == "Changed"
        assert (
            await client.put(
                f"{base}/{mid}", json={"content": "Stale", "expected_revision": 1}
            )
        ).status_code == 409
        assert (
            await client.post(base, json={"request_key": "one", "content": "Other"})
        ).status_code == 409
        app.dependency_overrides[get_current_owner_id] = lambda: uuid4()
        assert (await client.get(base)).status_code == 404
        assert (
            await client.post(base, json={"request_key": "intruder", "content": "No"})
        ).status_code == 404
        assert (
            await client.put(
                f"{base}/{mid}", json={"content": "No", "expected_revision": 2}
            )
        ).status_code == 404
        assert (await client.delete(f"{base}/{mid}")).status_code == 404
        app.dependency_overrides[get_current_owner_id] = lambda: owner.id
        response = await client.delete(f"{base}/{mid}")
        assert response.status_code == 200 and response.json() == {"deleted_count": 1}
        assert (await client.delete(f"{base}/{mid}")).status_code == 404
        assert len((await client.get(base)).json()["items"]) == 1
