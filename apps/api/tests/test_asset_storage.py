# 임시 로컬 경로와 FakeS3Client로 공통 저장 계약을 확인한다. 로컬 쓰기 실패 시 이전 파일 보존도 검사한다.
from __future__ import annotations

import io
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from app.modules.asset_storage import (
    AssetNotFoundError,
    AssetStorageAdapter,
    AssetStorageConfigurationError,
    AssetStorageError,
    AssetStorageErrorKind,
    AssetStorageSettings,
    DeleteAssetCommand,
    ExecutionEnvironment,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    S3StorageSettings,
    StorageKind,
    StoreAssetCommand,
    TestLocalStorageSettings,
    create_asset_storage_service,
    load_asset_storage_settings,
)
from app.modules.asset_storage.adapters import S3StorageAdapter, TestLocalStorageAdapter
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError

pytestmark = pytest.mark.asyncio


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.thread_ids: list[int] = []
        self.error: Exception | None = None
        self.closed = False

    def _record(self, operation: str, kwargs: dict) -> None:
        self.calls.append((operation, kwargs))
        self.thread_ids.append(threading.get_ident())
        if self.error is not None:
            raise self.error

    def upload_fileobj(self, **kwargs) -> None:
        self._record("upload_fileobj", kwargs)
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = (
            kwargs["Fileobj"].read(),
            kwargs["ExtraArgs"]["ContentType"],
        )

    def get_object(self, **kwargs):
        self._record("get_object", kwargs)
        try:
            content, content_type = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise _client_error("NoSuchKey", 404, "GetObject") from exc
        return {
            "Body": io.BytesIO(content),
            "ContentLength": len(content),
            "ContentType": content_type,
            "ETag": '"fake-etag"',
            "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

    def head_object(self, **kwargs):
        self._record("head_object", kwargs)
        try:
            content, content_type = self.objects[(kwargs["Bucket"], kwargs["Key"])]
        except KeyError as exc:
            raise _client_error("NoSuchKey", 404, "HeadObject") from exc
        return {
            "ContentLength": len(content),
            "ContentType": content_type,
            "ETag": '"fake-etag"',
            "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        }

    def delete_object(self, **kwargs) -> None:
        self._record("delete_object", kwargs)
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)

    def close(self) -> None:
        self.closed = True


def _client_error(code: str, status: int, operation: str) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {
                "HTTPStatusCode": status,
                "RequestId": "request-123",
            },
        },
        operation,
    )


def _local_adapter(tmp_path: Path) -> TestLocalStorageAdapter:
    return TestLocalStorageAdapter(
        TestLocalStorageSettings(storage_id="local-a", root=tmp_path)
    )


def _s3_adapter(client: FakeS3Client) -> S3StorageAdapter:
    return S3StorageAdapter(
        S3StorageSettings(
            storage_id="seoul-assets",
            bucket="asset-bucket",
            region="ap-northeast-2",
            key_prefix="tenant-data",
            max_attempts=1,
        ),
        client=client,
    )


@pytest.mark.parametrize("adapter_name", ["test_local", "s3"])
async def test_adapters_share_store_read_metadata_overwrite_delete_contract(
    adapter_name, tmp_path
):
    client = FakeS3Client()
    adapter = _local_adapter(tmp_path) if adapter_name == "test_local" else _s3_adapter(client)
    assert isinstance(adapter, AssetStorageAdapter)
    key = "characters/alpha/avatar.bin"
    first = b"\x00first\xff"

    stored = await adapter.store_asset(
        StoreAssetCommand(key, io.BytesIO(first), len(first), "application/octet-stream")
    )
    assert stored.storage_kind.value == adapter_name
    assert stored.storage_id in {"local-a", "seoul-assets"}
    assert stored.object_key == key
    assert stored.size_bytes == len(first)
    assert stored.content_type == "application/octet-stream"

    metadata = await adapter.get_asset_metadata(GetAssetMetadataCommand(key))
    assert metadata.object_key == key
    assert metadata.size_bytes == len(first)
    assert metadata.content_type == "application/octet-stream"

    opened = await adapter.read_asset(ReadAssetCommand(key))
    async with opened:
        assert await opened.read(2) + await opened.read() == first
    with pytest.raises(ValueError, match="closed"):
        await opened.read()

    second = b"replacement"
    await adapter.store_asset(
        StoreAssetCommand(key, io.BytesIO(second), len(second), "text/plain")
    )
    async with await adapter.read_asset(ReadAssetCommand(key)) as replacement:
        assert await replacement.read() == second
        assert replacement.metadata.content_type == "text/plain"

    await adapter.delete_asset(DeleteAssetCommand(key))
    await adapter.delete_asset(DeleteAssetCommand(key))
    with pytest.raises(AssetNotFoundError):
        await adapter.read_asset(ReadAssetCommand(key))
    with pytest.raises(AssetNotFoundError):
        await adapter.get_asset_metadata(GetAssetMetadataCommand(key))


@pytest.mark.parametrize(
    "object_key",
    [
        "../outside.bin",
        "/absolute.bin",
        "C:/outside.bin",
        r"nested\outside.bin",
        "nested//file.bin",
        ".asset_storage/metadata/file.json",
        "CON/file.bin",
    ],
)
async def test_object_keys_cannot_escape_or_use_nonportable_paths(object_key):
    with pytest.raises(ValueError, match="object_key"):
        ReadAssetCommand(object_key)


async def test_failed_local_write_leaves_previous_complete_object(tmp_path):
    adapter = _local_adapter(tmp_path)
    key = "safe/file.bin"
    original = b"complete"
    await adapter.store_asset(
        StoreAssetCommand(key, io.BytesIO(original), len(original), "application/test")
    )

    class FailingStream:
        calls = 0

        def read(self, size=-1):
            self.calls += 1
            if self.calls == 1:
                return b"partial"
            raise OSError("source failed")

    with pytest.raises(AssetStorageError):
        await adapter.store_asset(
            StoreAssetCommand(key, FailingStream(), 20, "application/test")
        )
    async with await adapter.read_asset(ReadAssetCommand(key)) as opened:
        assert await opened.read() == original
    assert not list(tmp_path.rglob("*.tmp"))


async def test_local_write_rejects_incorrect_declared_size_without_publishing(tmp_path):
    adapter = _local_adapter(tmp_path)
    with pytest.raises(AssetStorageError) as caught:
        await adapter.store_asset(
            StoreAssetCommand("file.bin", io.BytesIO(b"short"), 100, "text/plain")
        )
    assert caught.value.kind is AssetStorageErrorKind.DATA_INTEGRITY
    with pytest.raises(AssetNotFoundError):
        await adapter.get_asset_metadata(GetAssetMetadataCommand("file.bin"))


async def test_settings_loading_and_factory_selection(tmp_path):
    settings = load_asset_storage_settings(
        {
            "ENVIRONMENT": "test",
            "ASSET_STORAGE_KIND": "test_local",
            "ASSET_STORAGE_ID": "temporary",
            "ASSET_TEST_LOCAL_ROOT": str(tmp_path),
        }
    )
    service = create_asset_storage_service(settings)
    result = await service.store_asset(
        StoreAssetCommand("ok.bin", io.BytesIO(b"ok"), 2, "application/test")
    )
    assert result.storage_kind is StorageKind.TEST_LOCAL
    await service.aclose()

    client = FakeS3Client()
    s3_settings = load_asset_storage_settings(
        {
            "ENVIRONMENT": "test",
            "ASSET_STORAGE_KIND": "s3",
            "ASSET_STORAGE_ID": "integration-test-bucket",
            "ASSET_S3_BUCKET": "bucket",
            "ASSET_S3_REGION": "ap-northeast-2",
            "ASSET_S3_KEY_PREFIX": "prefix",
            "ASSET_S3_MAX_ATTEMPTS": "1",
        }
    )
    s3_service = create_asset_storage_service(s3_settings, s3_client=client)
    stored = await s3_service.store_asset(
        StoreAssetCommand("ok.bin", io.BytesIO(b"ok"), 2, "application/test")
    )
    assert stored.storage_kind is StorageKind.S3
    await s3_service.aclose()
    assert client.closed is False  # injected clients remain caller-owned


async def test_production_rejects_test_local_and_invalid_s3_settings(tmp_path):
    with pytest.raises(AssetStorageConfigurationError, match="forbidden"):
        AssetStorageSettings(
            environment=ExecutionEnvironment.PRODUCTION,
            storage_kind=StorageKind.TEST_LOCAL,
            test_local=TestLocalStorageSettings(root=tmp_path),
        )
    with pytest.raises(AssetStorageConfigurationError, match="ASSET_STORAGE_ID"):
        load_asset_storage_settings(
            {
                "ENVIRONMENT": "production",
                "ASSET_STORAGE_KIND": "s3",
                "ASSET_S3_BUCKET": "bucket",
                "ASSET_S3_REGION": "ap-northeast-2",
            }
        )
    with pytest.raises(AssetStorageConfigurationError, match="required"):
        load_asset_storage_settings({"ENVIRONMENT": "test"})


async def test_s3_maps_requests_prefixes_and_runs_sync_client_off_event_loop():
    client = FakeS3Client()
    adapter = _s3_adapter(client)
    main_thread = threading.get_ident()
    content = b"payload"
    await adapter.store_asset(
        StoreAssetCommand("a/file.bin", io.BytesIO(content), len(content), "image/png")
    )
    await adapter.get_asset_metadata(GetAssetMetadataCommand("a/file.bin"))
    async with await adapter.read_asset(ReadAssetCommand("a/file.bin")) as opened:
        assert await opened.read() == content
    await adapter.delete_asset(DeleteAssetCommand("a/file.bin"))

    assert [name for name, _ in client.calls] == [
        "upload_fileobj",
        "head_object",
        "get_object",
        "delete_object",
    ]
    for _, kwargs in client.calls:
        assert kwargs["Bucket"] == "asset-bucket"
        assert kwargs["Key"] == "tenant-data/a/file.bin"
    upload = client.calls[0][1]
    assert upload["ExtraArgs"] == {"ContentType": "image/png"}
    assert all(thread_id != main_thread for thread_id in client.thread_ids)


@pytest.mark.parametrize(
    "error,kind,retryable",
    [
        (
            _client_error("AccessDenied", 403, "HeadObject"),
            AssetStorageErrorKind.ACCESS_DENIED,
            False,
        ),
        (
            EndpointConnectionError(endpoint_url="https://s3.invalid"),
            AssetStorageErrorKind.CONNECTION,
            True,
        ),
        (
            ReadTimeoutError(endpoint_url="https://s3.invalid", error="timeout"),
            AssetStorageErrorKind.TIMEOUT,
            True,
        ),
        (
            _client_error("InternalError", 500, "HeadObject"),
            AssetStorageErrorKind.PROVIDER,
            True,
        ),
    ],
)
async def test_s3_translates_representative_provider_errors(error, kind, retryable):
    client = FakeS3Client()
    client.error = error
    adapter = _s3_adapter(client)
    with pytest.raises(AssetStorageError) as caught:
        await adapter.get_asset_metadata(GetAssetMetadataCommand("file.bin"))
    assert caught.value.kind is kind
    assert caught.value.retryable is retryable
    assert caught.value.object_key == "file.bin"
    assert caught.value.__cause__ is error


async def test_s3_delete_treats_provider_not_found_as_idempotent_success():
    client = FakeS3Client()
    client.error = _client_error("NoSuchKey", 404, "DeleteObject")
    await _s3_adapter(client).delete_asset(DeleteAssetCommand("missing.bin"))


async def test_factory_owned_s3_client_is_closed(monkeypatch):
    client = FakeS3Client()
    monkeypatch.setattr(
        "app.modules.asset_storage.adapters.s3_storage.adapter.boto3.client",
        lambda *args, **kwargs: client,
    )
    settings = AssetStorageSettings(
        environment=ExecutionEnvironment.TEST,
        storage_kind=StorageKind.S3,
        s3=S3StorageSettings("s3-a", "bucket", "ap-northeast-2"),
    )
    service = create_asset_storage_service(settings)
    await service.aclose()
    assert client.closed is True
