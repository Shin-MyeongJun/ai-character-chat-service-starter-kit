"""Binary transport ownership and cleanup, without database/provider I/O."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Scope

from app.http import character_dependencies, dependencies
from app.http import media as Http
from app.modules.asset_storage import types as StorageTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.product import types as ProductTypes


@dataclass
class Transport:
    app: FastAPI
    client: TestClient
    service: AsyncMock
    files: list[SpooledTemporaryFile[bytes]]
    character_owner: UUID
    product_owner: UUID


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> Iterator[Transport]:
    files: list[SpooledTemporaryFile[bytes]] = []

    def temporary(*, max_size: int) -> SpooledTemporaryFile[bytes]:
        content = SpooledTemporaryFile(max_size=max_size)
        files.append(content)
        return content

    monkeypatch.setattr(Http, "SpooledTemporaryFile", temporary)
    app = FastAPI()
    app.include_router(Http.router)
    service = AsyncMock()
    app.state.character_media_service = service
    app.state.product_media_service = service
    character_owner, product_owner = uuid4(), uuid4()
    app.dependency_overrides[character_dependencies.get_current_owner_id] = lambda: (
        character_owner
    )
    app.dependency_overrides[dependencies.get_current_owner_id] = lambda: product_owner
    with TestClient(app) as client:
        yield Transport(app, client, service, files, character_owner, product_owner)


@pytest.mark.parametrize("outcome", ["success", "invalid", "failure"])
def test_upload_binary_file_is_open_during_service_and_closed_after_every_outcome(
    transport: Transport, outcome: str
) -> None:
    item = transport
    character_id, request_id, media_id = uuid4(), uuid4(), uuid4()
    payload = b"\x00\xff" * (1024 * 1024 // 2 + 4)

    async def upload(
        command: CharacterTypes.UploadCharacterMediaCommand,
    ) -> SimpleNamespace:
        assert command.character_id == character_id
        assert command.owner_id == item.character_owner
        assert command.request_id == request_id
        assert not command.content.closed
        # HTTP leaves the file at EOF; the media service owns fingerprint rewinds.
        assert command.content.tell() == len(payload)
        command.content.seek(0)
        assert command.content.read() == payload
        if outcome == "invalid":
            raise ValueError("private invalid input detail")
        if outcome == "failure":
            raise RuntimeError("storage interrupted")
        return SimpleNamespace(
            id=media_id,
            content_url=f"/characters/media/{media_id}/content",
            content_type="image/png",
            size_bytes=len(payload),
            original_filename="portrait.png",
            purpose="portrait",
        )

    item.service.upload_character_media.side_effect = upload
    headers = {
        "Content-Type": "image/png",
        "Idempotency-Key": str(request_id),
        "X-Filename": "portrait.png",
        "X-Media-Purpose": "portrait",
    }
    if outcome == "failure":
        with pytest.raises(RuntimeError, match="storage interrupted"):
            item.client.post(
                f"/characters/{character_id}/media/uploads",
                content=payload,
                headers=headers,
            )
    else:
        response = item.client.post(
            f"/characters/{character_id}/media/uploads",
            content=payload,
            headers=headers,
        )
        assert response.status_code == (201 if outcome == "success" else 422)
        if outcome == "success":
            assert response.json()["media_id"] == str(media_id)
            assert response.json()["size_bytes"] == len(payload)
        else:
            assert "private" not in response.text
    assert len(item.files) == 1 and item.files[0].closed


def test_oversized_upload_closes_spool_without_calling_service(
    transport: Transport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Http, "MAX_MEDIA_BYTES", 4)
    response = transport.client.post(
        f"/characters/{uuid4()}/media/uploads",
        content=b"12345",
        headers={
            "Content-Type": "image/png",
            "Idempotency-Key": str(uuid4()),
            "X-Filename": "portrait.png",
            "X-Media-Purpose": "portrait",
        },
    )
    assert response.status_code == 413
    transport.service.upload_character_media.assert_not_awaited()
    assert len(transport.files) == 1 and transport.files[0].closed


def opened_media(reader: AsyncMock) -> StorageTypes.AssetReadInfo:
    return StorageTypes.AssetReadInfo(
        StorageTypes.AssetMetadataInfo(
            StorageTypes.StorageKind.TEST_LOCAL, "test", "key", 7, "image/png"
        ),
        reader,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "read_error", "cancelled"])
async def test_reader_closes_and_original_stream_failure_propagates(
    outcome: str,
) -> None:
    reader = AsyncMock()
    reader.read.side_effect = (
        [b"payload", b""]
        if outcome == "success"
        else RuntimeError("read failed")
        if outcome == "read_error"
        else asyncio.CancelledError()
    )
    response = Http.MediaStreamingResponse(opened_media(reader))
    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    send = AsyncMock()
    if outcome == "success":
        await response(scope, AsyncMock(), send)
        assert send.await_args_list[-1].args[0]["more_body"] is False
    else:
        error = RuntimeError if outcome == "read_error" else asyncio.CancelledError
        with pytest.raises(error):
            await response(scope, AsyncMock(), send)
    assert send.await_args_list[0].args[0]["status"] == 200
    assert all(call.args == (64 * 1024,) for call in reader.read.await_args_list)
    reader.aclose.assert_awaited_once()


@pytest.mark.parametrize("kind", ["character", "product"])
def test_download_forwards_actor_scope_and_preserves_headers_and_schema(
    transport: Transport, kind: str
) -> None:
    item = transport
    media_id, product_id, snapshot_id = uuid4(), uuid4(), uuid4()
    reader = AsyncMock()
    reader.read.side_effect = [b"payload", b""]
    command: (
        CharacterTypes.ReadCharacterMediaCommand | ProductTypes.ReadProductMediaCommand
    )
    if kind == "character":
        operation = item.service.read_character_media
        path = f"/characters/media/{media_id}/content"
        command = CharacterTypes.ReadCharacterMediaCommand(
            media_id, item.character_owner
        )
        template = "/characters/media/{media_id}/content"
    else:
        operation = item.service.read_product_media
        path = f"/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content"
        command = ProductTypes.ReadProductMediaCommand(
            product_id, snapshot_id, media_id, item.product_owner
        )
        template = (
            "/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content"
        )
    operation.return_value = opened_media(reader)
    response = item.client.get(path)
    assert response.status_code == 200 and response.content == b"payload"
    assert response.headers["content-length"] == "7"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"] == "inline"
    operation.assert_awaited_once_with(command)
    reader.aclose.assert_awaited_once()
    schema = item.app.openapi()["paths"][template]["get"]["responses"]["200"]
    assert schema["content"]["application/json"]["schema"] == {}
