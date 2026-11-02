"""Offline S3 stream/metadata boundaries; no credentials or AWS requests."""

import io
from unittest.mock import Mock

import pytest
from botocore.exceptions import ReadTimeoutError
from test_asset_storage import FakeS3Client

from app.modules.asset_storage.adapters.s3_storage.adapter import (
    S3StorageAdapter,
    S3StorageClient,
)
from app.modules.asset_storage.types import (
    AssetStorageError,
    AssetStorageErrorKind,
    ReadAssetCommand,
    S3StorageSettings,
    StoreAssetCommand,
)


def adapter(client: S3StorageClient) -> S3StorageAdapter:
    return S3StorageAdapter(
        S3StorageSettings("test", "bucket", "ap-northeast-2", key_prefix="tenant"),
        client=client,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{}, {"ContentLength": "invalid"}])
async def test_bad_read_metadata_closes_provider_body_before_raising(
    fields: dict[str, object],
) -> None:
    body = io.BytesIO(b"payload")
    client = Mock()
    client.get_object.return_value = {"Body": body, **fields}
    with pytest.raises(AssetStorageError) as caught:
        await adapter(client).read_asset(ReadAssetCommand("asset.bin"))
    assert caught.value.kind is AssetStorageErrorKind.PROVIDER
    assert caught.value.operation == "read"
    assert caught.value.object_key == "asset.bin"
    assert isinstance(caught.value.__cause__, (KeyError, TypeError, ValueError))
    assert body.closed
    client.get_object.assert_called_once_with(Bucket="bucket", Key="tenant/asset.bin")


@pytest.mark.asyncio
async def test_metadata_conversion_keeps_fallbacks_and_reader_ownership() -> None:
    body = io.BytesIO(b"payload")
    client = Mock()
    client.get_object.return_value = {
        "Body": body,
        "ContentLength": "7",
        "ContentType": None,
        "ETag": '"quoted-etag"',
        "LastModified": "not-a-datetime",
        "extension": {"kept": True},
    }
    opened = await adapter(client).read_asset(ReadAssetCommand("asset.bin"))
    assert not body.closed
    assert opened.metadata.size_bytes == 7
    assert opened.metadata.content_type == "application/octet-stream"
    assert opened.metadata.etag == "quoted-etag"
    assert opened.metadata.last_modified is None
    assert await opened.read(3) == b"pay"
    assert await opened.read() == b"load"
    await opened.aclose()
    assert body.closed


@pytest.mark.asyncio
async def test_upload_preserves_current_stream_offset_and_caller_owned_lifetime() -> (
    None
):
    client = FakeS3Client()
    content = io.BytesIO(b"prefixpayload")
    content.seek(6)
    result = await adapter(client).store_asset(
        StoreAssetCommand("asset.bin", content, 7, "image/png")
    )
    assert result.size_bytes == 7
    assert client.objects[("bucket", "tenant/asset.bin")] == (b"payload", "image/png")
    assert not content.closed and content.tell() == 13
    await adapter(client).aclose()
    assert client.closed is False
    content.close()


@pytest.mark.asyncio
async def test_nonseekable_upload_keeps_declared_size_trust_without_copy() -> None:
    class NonSeekable(io.BytesIO):
        def tell(self) -> int:
            raise OSError("position is unavailable")

        def seekable(self) -> bool:
            return False

    client = FakeS3Client()
    content = NonSeekable(b"payload")
    result = await adapter(client).store_asset(
        StoreAssetCommand("asset.bin", content, 99, "image/png")
    )
    assert result.size_bytes == 99
    assert client.objects[("bucket", "tenant/asset.bin")][0] == b"payload"
    assert not content.closed
    content.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["read", "close"])
async def test_provider_reader_failures_keep_cause_and_idempotent_close(
    operation: str,
) -> None:
    failure = ReadTimeoutError(endpoint_url="https://s3.invalid")
    body = Mock()
    body.read.return_value = b"payload"
    getattr(body, operation).side_effect = failure
    client = Mock()
    client.get_object.return_value = {"Body": body, "ContentLength": 7}
    opened = await adapter(client).read_asset(ReadAssetCommand("asset.bin"))
    with pytest.raises(AssetStorageError) as caught:
        if operation == "read":
            await opened.read()
        else:
            await opened.aclose()
    assert caught.value.kind is AssetStorageErrorKind.TIMEOUT
    assert caught.value.operation == "read"
    assert caught.value.__cause__ is failure
    await opened.aclose()
    body.close.assert_called_once()
