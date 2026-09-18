# 로컬 본문과 메타데이터를 별도 파일로 저장하고 키별 asyncio.Lock으로 이 인스턴스의 접근을 직렬화한다.
# 임시 파일 교체 실패 시 메타데이터 복원을 시도한다. 여러 프로세스나 두 파일의 동시 원자성을 보장하지 않는다.
# 읽기 메타데이터 검사는 파일 크기를 비교하며 본문 해시를 다시 계산하지 않는다.
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.modules.asset_storage.types import (
    AssetMetadataInfo,
    AssetNotFoundError,
    AssetReadInfo,
    AssetStorageError,
    AssetStorageErrorKind,
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    StorageKind,
    StoreAssetCommand,
    StoredAssetInfo,
    TestLocalStorageSettings,
)

_COPY_CHUNK_SIZE = 1024 * 1024


class _LocalAssetReader:
    def __init__(
        self,
        file_object,
        error_mapper: Callable[[OSError], AssetStorageError],
    ) -> None:
        self._file_object = file_object
        self._error_mapper = error_mapper

    async def read(self, size: int = -1) -> bytes:
        try:
            return await asyncio.to_thread(self._file_object.read, size)
        except OSError as exc:
            raise self._error_mapper(exc) from exc

    async def aclose(self) -> None:
        try:
            await asyncio.to_thread(self._file_object.close)
        except OSError as exc:
            raise self._error_mapper(exc) from exc


class TestLocalStorageAdapter:
    """Filesystem adapter intended only for tests and explicit local development."""

    __test__ = False
    storage_kind = StorageKind.TEST_LOCAL

    def __init__(self, settings: TestLocalStorageSettings) -> None:
        settings.root.mkdir(parents=True, exist_ok=True)
        if not settings.root.is_dir():
            raise ValueError("The test_local storage root must be a directory.")
        self._root = settings.root.resolve(strict=True)
        self.storage_id = settings.storage_id
        self._metadata_root = self._root / ".asset_storage" / "metadata"
        self._metadata_root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, object_key: str) -> asyncio.Lock:
        return self._locks.setdefault(object_key, asyncio.Lock())

    def _data_path(self, object_key: str) -> Path:
        candidate = self._root.joinpath(*object_key.split("/"))
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise ValueError("object_key resolves outside the test_local storage root.")
        return resolved

    def _metadata_path(self, object_key: str) -> Path:
        digest = hashlib.sha256(object_key.encode("utf-8")).hexdigest()
        return self._metadata_root / f"{digest}.json"

    def _map_os_error(
        self, exc: OSError, *, operation: str, object_key: str
    ) -> AssetStorageError:
        if isinstance(exc, FileNotFoundError):
            return AssetNotFoundError(
                f"Asset {object_key!r} was not found.",
                kind=AssetStorageErrorKind.NOT_FOUND,
                operation=operation,
                object_key=object_key,
            )
        kind = (
            AssetStorageErrorKind.ACCESS_DENIED
            if isinstance(exc, PermissionError)
            else AssetStorageErrorKind.PROVIDER
        )
        return AssetStorageError(
            f"test_local {operation} failed for asset {object_key!r}.",
            kind=kind,
            operation=operation,
            object_key=object_key,
        )

    def _store_sync(self, command: StoreAssetCommand) -> StoredAssetInfo:
        data_path = self._data_path(command.object_key)
        metadata_path = self._metadata_path(command.object_key)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = f".{uuid4().hex}.tmp"
        data_temp = data_path.with_name(data_path.name + suffix)
        metadata_temp = metadata_path.with_name(metadata_path.name + suffix)
        previous_metadata = (
            metadata_path.read_bytes() if metadata_path.is_file() else None
        )
        replaced_metadata = False
        try:
            digest = hashlib.sha256()
            written = 0
            with data_temp.open("xb") as destination:
                while True:
                    chunk = command.content.read(_COPY_CHUNK_SIZE)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("content.read() must return bytes.")
                    destination.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            if written != command.size_bytes:
                raise AssetStorageError(
                    "The stream length does not match size_bytes.",
                    kind=AssetStorageErrorKind.DATA_INTEGRITY,
                    operation="store",
                    object_key=command.object_key,
                )

            last_modified = datetime.now(timezone.utc)
            etag = digest.hexdigest()
            metadata_temp.write_text(
                json.dumps(
                    {
                        "object_key": command.object_key,
                        "size_bytes": written,
                        "content_type": command.content_type,
                        "etag": etag,
                        "last_modified": last_modified.isoformat(),
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            os.replace(metadata_temp, metadata_path)
            replaced_metadata = True
            try:
                os.replace(data_temp, data_path)
            except BaseException:
                if previous_metadata is None:
                    metadata_path.unlink(missing_ok=True)
                else:
                    rollback = metadata_path.with_name(metadata_path.name + suffix)
                    rollback.write_bytes(previous_metadata)
                    os.replace(rollback, metadata_path)
                raise
            return StoredAssetInfo(
                storage_kind=self.storage_kind,
                storage_id=self.storage_id,
                object_key=command.object_key,
                size_bytes=written,
                content_type=command.content_type,
                etag=etag,
                last_modified=last_modified,
            )
        finally:
            data_temp.unlink(missing_ok=True)
            metadata_temp.unlink(missing_ok=True)
            if replaced_metadata and not data_path.exists():
                metadata_path.unlink(missing_ok=True)

    def _read_metadata_sync(self, object_key: str) -> AssetMetadataInfo:
        data_path = self._data_path(object_key)
        metadata_path = self._metadata_path(object_key)
        if not data_path.is_file() or not metadata_path.is_file():
            raise FileNotFoundError(object_key)
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        actual_size = data_path.stat().st_size
        if raw.get("object_key") != object_key or raw.get("size_bytes") != actual_size:
            raise AssetStorageError(
                f"Stored metadata is inconsistent for asset {object_key!r}.",
                kind=AssetStorageErrorKind.DATA_INTEGRITY,
                operation="metadata",
                object_key=object_key,
            )
        return AssetMetadataInfo(
            storage_kind=self.storage_kind,
            storage_id=self.storage_id,
            object_key=object_key,
            size_bytes=actual_size,
            content_type=str(raw["content_type"]),
            etag=str(raw["etag"]),
            last_modified=datetime.fromisoformat(raw["last_modified"]),
        )

    def _open_sync(self, object_key: str):
        metadata = self._read_metadata_sync(object_key)
        return metadata, self._data_path(object_key).open("rb")

    async def store_asset(self, command: StoreAssetCommand) -> StoredAssetInfo:
        async with self._lock_for(command.object_key):
            try:
                return await asyncio.to_thread(self._store_sync, command)
            except AssetStorageError:
                raise
            except OSError as exc:
                raise self._map_os_error(
                    exc, operation="store", object_key=command.object_key
                ) from exc

    async def read_asset(self, command: ReadAssetCommand) -> AssetReadInfo:
        async with self._lock_for(command.object_key):
            try:
                metadata, file_object = await asyncio.to_thread(
                    self._open_sync, command.object_key
                )
            except AssetStorageError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise AssetStorageError(
                    f"Stored metadata is invalid for asset {command.object_key!r}.",
                    kind=AssetStorageErrorKind.DATA_INTEGRITY,
                    operation="read",
                    object_key=command.object_key,
                ) from exc
            except OSError as exc:
                raise self._map_os_error(
                    exc, operation="read", object_key=command.object_key
                ) from exc
        return AssetReadInfo(
            metadata,
            _LocalAssetReader(
                file_object,
                lambda exc: self._map_os_error(
                    exc, operation="read", object_key=command.object_key
                ),
            ),
        )

    async def delete_asset(self, command: DeleteAssetCommand) -> None:
        async with self._lock_for(command.object_key):
            try:
                await asyncio.to_thread(self._delete_sync, command.object_key)
            except OSError as exc:
                raise self._map_os_error(
                    exc, operation="delete", object_key=command.object_key
                ) from exc

    def _delete_sync(self, object_key: str) -> None:
        self._data_path(object_key).unlink(missing_ok=True)
        self._metadata_path(object_key).unlink(missing_ok=True)

    async def get_asset_metadata(
        self, command: GetAssetMetadataCommand
    ) -> AssetMetadataInfo:
        async with self._lock_for(command.object_key):
            try:
                return await asyncio.to_thread(
                    self._read_metadata_sync, command.object_key
                )
            except AssetStorageError:
                raise
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise AssetStorageError(
                    f"Stored metadata is invalid for asset {command.object_key!r}.",
                    kind=AssetStorageErrorKind.DATA_INTEGRITY,
                    operation="metadata",
                    object_key=command.object_key,
                ) from exc
            except OSError as exc:
                raise self._map_os_error(
                    exc, operation="metadata", object_key=command.object_key
                ) from exc

    async def aclose(self) -> None:
        return None
