# 로컬 본문과 메타데이터를 별도 파일로 저장하고 키별 asyncio.Lock으로 이 인스턴스의 접근을 직렬화한다.
# 임시 파일 교체 실패 시 메타데이터 복원을 시도한다. 여러 프로세스나 두 파일의 동시 원자성을 보장하지 않는다.
# 읽기 메타데이터 검사는 파일 크기를 비교하며 본문 해시를 다시 계산하지 않는다.
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import BinaryIO, TypeVar
from uuid import uuid4
from weakref import WeakValueDictionary

if sys.platform == "win32":
    import _winapi
    import msvcrt

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
_T = TypeVar("_T")


async def _settle_task(
    task: asyncio.Task[_T],
) -> tuple[_T, asyncio.CancelledError | None]:
    """Own a worker until completion; cancellation cannot stop its file operation."""
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            if cancellation is None:
                cancellation = exc
        except Exception:
            break  # Retrieve the failure below, also when cancellation is pending.
    try:
        return task.result(), cancellation
    except (Exception, asyncio.CancelledError):
        if cancellation is not None:
            raise cancellation from None
        raise


async def _run_io(operation: Callable[[], _T]) -> _T:
    result, cancellation = await _settle_task(
        asyncio.create_task(asyncio.to_thread(operation))
    )
    if cancellation is not None:
        raise cancellation
    return result


def _open_binary(path: Path) -> BinaryIO:
    if sys.platform == "win32":
        # CPython's Windows wrapper supplies FILE_SHARE_READ | FILE_SHARE_DELETE.
        # Readers keep their open file version while its logical key is removed.
        handle = _winapi.CreateFile(
            str(path), _winapi.GENERIC_READ, 0x1 | 0x4, 0, _winapi.OPEN_EXISTING, 0, 0
        )
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            _winapi.CloseHandle(handle)
            raise
        try:
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)  # The descriptor owns handle after open_osfhandle.
            raise
    return path.open("rb")


def _replace_data(source: Path, destination: Path) -> None:
    try:
        os.replace(source, destination)
    except PermissionError:
        if sys.platform != "win32" or not destination.is_file():
            raise
        # Windows replacement can reject an open destination even with delete
        # sharing. Retire its name, publish the new file, then unlink the old one.
        retired = destination.with_name(f"{destination.name}.{uuid4().hex}.old")
        os.replace(destination, retired)
        try:
            os.replace(source, destination)
            retired.unlink()
        except BaseException:
            os.replace(retired, destination)
            raise


class _LocalAssetReader:
    def __init__(
        self,
        file_object: BinaryIO,
        error_mapper: Callable[[OSError], AssetStorageError],
    ) -> None:
        self._file_object = file_object
        self._error_mapper = error_mapper
        self._lock = asyncio.Lock()

    async def read(self, size: int = -1) -> bytes:
        async with self._lock:
            try:
                return await _run_io(partial(self._file_object.read, size))
            except OSError as exc:
                raise self._error_mapper(exc) from exc

    async def aclose(self) -> None:
        _, cancellation = await _settle_task(asyncio.create_task(self._close()))
        if cancellation is not None:
            raise cancellation

    async def _close(self) -> None:
        async with self._lock:
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
        # Holders and waiters retain the lock. Idle keys do not accumulate here.
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

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
                _replace_data(data_temp, data_path)
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

    def _open_sync(self, object_key: str) -> tuple[AssetMetadataInfo, BinaryIO]:
        metadata = self._read_metadata_sync(object_key)
        return metadata, _open_binary(self._data_path(object_key))

    async def store_asset(self, command: StoreAssetCommand) -> StoredAssetInfo:
        async with self._lock_for(command.object_key):
            try:
                return await _run_io(partial(self._store_sync, command))
            except AssetStorageError:
                raise
            except OSError as exc:
                raise self._map_os_error(
                    exc, operation="store", object_key=command.object_key
                ) from exc

    async def read_asset(self, command: ReadAssetCommand) -> AssetReadInfo:
        opened, cancellation = await _settle_task(
            asyncio.create_task(self._open_asset(command))
        )
        if cancellation is not None:
            try:
                await _settle_task(asyncio.create_task(opened.aclose()))
            finally:
                raise cancellation
        return opened

    async def _open_asset(self, command: ReadAssetCommand) -> AssetReadInfo:
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
                await _run_io(partial(self._delete_sync, command.object_key))
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
                return await _run_io(
                    partial(self._read_metadata_sync, command.object_key)
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
