from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from app.http import character_dependencies, dependencies
from app.http.media import MediaStreamingResponse, router
from app.modules.asset_storage import types as StorageTypes
from app.modules.content.character.router import router as characters
from app.modules.content.product.service.views.media import ProductMediaService
from fastapi import FastAPI
from starlette.requests import ClientDisconnect
from test_character_media import media  # noqa: F401 - parametrized storage fixture
from test_product_integration import seed

pytestmark = pytest.mark.asyncio


async def test_binary_upload_existing_json_contract_and_owner_only_streaming(db, media):  # noqa: F811
    owner, character, _ = await seed(db)
    app = FastAPI()
    app.include_router(router)
    app.include_router(characters)
    app.state.character_media_service = media
    app.state.product_media_service = ProductMediaService(media.sessions, media)
    auth = {"owner": owner.id}

    async def session():
        async with media.sessions() as value:
            yield value

    app.dependency_overrides[character_dependencies.get_current_owner_id] = lambda: (
        auth["owner"]
    )
    app.dependency_overrides[character_dependencies.get_character_session] = session
    headers = {
        "Content-Type": "image/png",
        "Idempotency-Key": str(uuid4()),
        "X-Filename": "portrait.png",
        "X-Media-Purpose": "portrait",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/characters/{character.id}/media/uploads",
            content=b"picture",
            headers=headers,
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert set(result) == {
            "media_id",
            "content_url",
            "content_type",
            "size_bytes",
            "original_filename",
            "purpose",
        }
        assert (
            result["content_url"] == f"/characters/media/{result['media_id']}/content"
        )
        retry = await client.post(
            f"/characters/{character.id}/media/uploads",
            content=b"picture",
            headers=headers,
        )
        assert retry.json() == result
        image = await client.post(
            "/characters/images",
            json={
                "character_id": str(character.id),
                "emotion_tag": "normal",
                "image_url": result["content_url"],
            },
        )
        assert image.status_code == 201, image.text
        assert set(image.json()["image"]) == {
            "id",
            "character_id",
            "emotion_tag",
            "image_url",
            "is_default",
            "created_at",
            "updated_at",
        }
        assert image.json()["image"]["image_url"] == result["content_url"]
        content = await client.get(result["content_url"])
        assert content.content == b"picture"
        assert content.headers["cache-control"] == "private, no-store"
        assert content.headers["x-content-type-options"] == "nosniff"
        auth["owner"] = uuid4()
        assert (await client.get(result["content_url"])).status_code == 404
        assert (
            await client.post(
                f"/characters/{character.id}/media/uploads",
                content=b"picture",
                headers=headers,
            )
        ).status_code == 404
        app.dependency_overrides.pop(character_dependencies.get_current_owner_id)
        assert (
            await client.get(result["content_url"])
        ).status_code == 503  # existing unconfigured auth fails closed


async def test_storage_errors_never_expose_local_paths_or_provider_details(monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[character_dependencies.get_current_owner_id] = lambda: (
        uuid4()
    )
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: uuid4()
    failure = StorageTypes.AssetStorageError(
        "secret absolute path C:/private/bucket",
        kind=StorageTypes.AssetStorageErrorKind.PROVIDER,
        operation="read",
        object_key="private",
    )
    service = AsyncMock()
    service.read_character_media.side_effect = failure
    app.state.character_media_service = service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/characters/media/{uuid4()}/content")
        assert response.status_code == 503
        assert "private" not in response.text


async def test_stream_reader_closes_when_send_fails():
    reader = AsyncMock()
    reader.read.return_value = b"payload"
    opened = StorageTypes.AssetReadInfo(
        StorageTypes.AssetMetadataInfo(
            StorageTypes.StorageKind.TEST_LOCAL, "test", "key", 7, "image/png"
        ),
        reader,
    )
    response = MediaStreamingResponse(opened)

    async def send(message):
        raise OSError("disconnected")

    with pytest.raises((OSError, ClientDisconnect)):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), send
        )
    reader.aclose.assert_awaited_once()
