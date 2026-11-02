"""Real local files and gated worker threads; no DB, S3 or provider requests."""

import asyncio
import hashlib
import io
import json
import os
import sys
import threading
from pathlib import Path
from typing import BinaryIO

import pytest

from app.modules.asset_storage.adapters.test_local_storage import adapter as Local
from app.modules.asset_storage.adapters.test_local_storage.adapter import (
    TestLocalStorageAdapter,
)
from app.modules.asset_storage.types import (
    AssetMetadataInfo,
    AssetNotFoundError,
    AssetStorageError,
    AssetStorageErrorKind,
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    StoreAssetCommand,
    TestLocalStorageSettings,
)

pytestmark = pytest.mark.asyncio


def adapter_at(root: Path) -> TestLocalStorageAdapter:
    return TestLocalStorageAdapter(TestLocalStorageSettings(root=root))


async def store(adapter: TestLocalStorageAdapter, key: str, content: bytes) -> None:
    with io.BytesIO(content) as stream:
        await adapter.store_asset(
            StoreAssetCommand(key, stream, len(content), "test/asset")
        )


async def test_idle_key_locks_are_reclaimed_after_success_and_failure(
    tmp_path: Path,
) -> None:
    adapter = adapter_at(tmp_path)
    for index in range(40):
        key = f"{index}.bin"
        await store(adapter, key, b"data")
        await adapter.get_asset_metadata(GetAssetMetadataCommand(key))
        async with await adapter.read_asset(ReadAssetCommand(key)) as opened:
            assert await opened.read() == b"data"
        await adapter.delete_asset(DeleteAssetCommand(key))
        with pytest.raises(AssetNotFoundError):
            await adapter.get_asset_metadata(GetAssetMetadataCommand(key))
    assert len(adapter._locks) == 0


async def test_delete_keeps_open_readers_and_allows_immediate_key_reuse(
    tmp_path: Path,
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"original")
    first = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    second = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    try:
        assert await first.read(3) == b"ori"
        await asyncio.wait_for(adapter.delete_asset(DeleteAssetCommand("asset.bin")), 5)
        await adapter.delete_asset(DeleteAssetCommand("asset.bin"))
        with pytest.raises(AssetNotFoundError):
            await adapter.read_asset(ReadAssetCommand("asset.bin"))
        with pytest.raises(AssetNotFoundError):
            await adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
        await store(adapter, "asset.bin", b"replacement")
        assert await first.read() == b"ginal"
        assert await second.read() == b"original"
        assert first.metadata.size_bytes == second.metadata.size_bytes == 8
    finally:
        await first.aclose()
        await second.aclose()
    async with await adapter.read_asset(ReadAssetCommand("asset.bin")) as current:
        assert await current.read() == b"replacement"
    assert len(adapter._locks) == 0


async def test_overwrite_preserves_each_open_file_version_and_metadata(
    tmp_path: Path,
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"original")
    first = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    try:
        assert await first.read(2) == b"or"
        await asyncio.wait_for(store(adapter, "asset.bin", b"second"), 5)
        second = await adapter.read_asset(ReadAssetCommand("asset.bin"))
        try:
            await store(adapter, "asset.bin", b"third")
            assert await first.read() == b"iginal"
            assert await second.read() == b"second"
            assert first.metadata.etag != second.metadata.etag
            async with await adapter.read_asset(
                ReadAssetCommand("asset.bin")
            ) as current:
                assert await current.read() == b"third"
        finally:
            await second.aclose()
    finally:
        await first.aclose()
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.old"))
    assert len(adapter._locks) == 0


class Gate:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.started = asyncio.Event()
        self.release = threading.Event()

    def wait(self) -> None:
        self.loop.call_soon_threadsafe(self.started.set)
        if not self.release.wait(5):
            raise TimeoutError("The test worker gate was not released.")


async def test_cancelled_store_retains_key_lock_until_worker_finishes(
    tmp_path: Path,
) -> None:
    adapter = adapter_at(tmp_path)
    gate = Gate()

    class Content(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            gate.wait()
            return super().read(size)

    content = Content(b"payload")
    task = asyncio.create_task(
        adapter.store_asset(StoreAssetCommand("asset.bin", content, 7, "test/asset"))
    )
    deletion: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(gate.started.wait(), 5)
        task.cancel("first cancellation")
        await asyncio.sleep(0)
        task.cancel("second cancellation")
        deletion = asyncio.create_task(
            adapter.delete_asset(DeleteAssetCommand("asset.bin"))
        )
        await asyncio.sleep(0)
        assert not task.done() and not deletion.done()
        await store(adapter, "independent.bin", b"independent")
        gate.release.set()
        with pytest.raises(asyncio.CancelledError) as error:
            await asyncio.wait_for(task, 5)
        assert error.value.args == ("first cancellation",)
        await asyncio.wait_for(deletion, 5)
        with pytest.raises(AssetNotFoundError):
            await adapter.read_asset(ReadAssetCommand("asset.bin"))
        assert not content.closed
    finally:
        gate.release.set()
        await asyncio.gather(
            task, *([deletion] if deletion else []), return_exceptions=True
        )
        content.close()
    assert len(adapter._locks) == 0


@pytest.mark.parametrize("cancel_waiter", [False, True])
async def test_waiting_same_key_operations_keep_one_lock_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_waiter: bool
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"payload")
    gate = Gate()
    delete_sync = adapter._delete_sync

    def delayed_delete(key: str) -> None:
        gate.wait()
        delete_sync(key)

    monkeypatch.setattr(adapter, "_delete_sync", delayed_delete)
    deletion = asyncio.create_task(
        adapter.delete_asset(DeleteAssetCommand("asset.bin"))
    )
    waiting = asyncio.create_task(
        adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
    )
    try:
        await asyncio.wait_for(gate.started.wait(), 5)
        await asyncio.sleep(0)
        assert len(adapter._locks) == 1 and not waiting.done()
        if cancel_waiter:
            waiting.cancel()
        deletion.cancel("stop delete")
        await asyncio.sleep(0)
        assert not deletion.done()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError, match="stop delete"):
            await asyncio.wait_for(deletion, 5)
        with pytest.raises(
            asyncio.CancelledError if cancel_waiter else AssetNotFoundError
        ):
            await waiting
    finally:
        gate.release.set()
        await asyncio.gather(deletion, waiting, return_exceptions=True)
    assert len(adapter._locks) == 0


@pytest.mark.parametrize("open_fails", [False, True])
async def test_cancelled_acquisition_closes_late_file_or_consumes_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, open_fails: bool
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"payload")
    gate = Gate()
    open_sync = adapter._open_sync
    files: list[BinaryIO] = []

    def delayed_open(key: str) -> tuple[AssetMetadataInfo, BinaryIO]:
        if open_fails:
            gate.wait()
            raise PermissionError("open failed")
        metadata, file = open_sync(key)
        files.append(file)
        gate.wait()
        return metadata, file

    monkeypatch.setattr(adapter, "_open_sync", delayed_open)
    task = asyncio.create_task(adapter.read_asset(ReadAssetCommand("asset.bin")))
    try:
        await asyncio.wait_for(gate.started.wait(), 5)
        task.cancel("first cancellation")
        await asyncio.sleep(0)
        task.cancel("second cancellation")
        await asyncio.sleep(0)
        assert not task.done()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError) as error:
            await asyncio.wait_for(task, 5)
        assert error.value.args == ("first cancellation",)
        assert all(file.closed for file in files)
    finally:
        gate.release.set()
        await asyncio.gather(task, return_exceptions=True)
        for file in files:
            file.close()
    assert len(adapter._locks) == 0


@pytest.mark.parametrize("cancel_close", [False, True])
async def test_cancelled_read_finishes_before_close_touches_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_close: bool
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"payload")
    metadata = await adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
    gate = Gate()

    class Stream(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            gate.wait()
            assert not self.closed
            return super().read(size)

    stream = Stream(b"payload")

    def open_sync(key: str) -> tuple[AssetMetadataInfo, BinaryIO]:
        return metadata, stream

    monkeypatch.setattr(adapter, "_open_sync", open_sync)
    opened = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    read = asyncio.create_task(opened.read())
    close: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(gate.started.wait(), 5)
        read.cancel("stop reading")
        close = asyncio.create_task(opened.aclose())
        await asyncio.sleep(0)
        assert not read.done() and not close.done() and not stream.closed
        if cancel_close:
            close.cancel("stop closing")
            await asyncio.sleep(0)
            assert not close.done()
        gate.release.set()
        with pytest.raises(asyncio.CancelledError, match="stop reading"):
            await read
        if cancel_close:
            with pytest.raises(asyncio.CancelledError, match="stop closing"):
                await asyncio.wait_for(close, 5)
        else:
            await asyncio.wait_for(close, 5)
        assert stream.closed
        await opened.aclose()
        with pytest.raises(ValueError, match="closed"):
            await opened.read()
    finally:
        gate.release.set()
        await asyncio.gather(read, *([close] if close else []), return_exceptions=True)
        stream.close()


async def test_os_error_translation_and_key_cleanup_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = adapter_at(tmp_path)
    failure = PermissionError("denied")

    def fail(key: str) -> None:
        raise failure

    monkeypatch.setattr(adapter, "_delete_sync", fail)
    with pytest.raises(AssetStorageError) as error:
        await adapter.delete_asset(DeleteAssetCommand("asset.bin"))
    assert error.value.kind is AssetStorageErrorKind.ACCESS_DENIED
    assert error.value.operation == "delete" and error.value.object_key == "asset.bin"
    assert error.value.__cause__ is failure
    assert len(adapter._locks) == 0


@pytest.mark.parametrize("close_fails", [False, True])
@pytest.mark.parametrize("cancel_close", [False, True])
async def test_close_owns_worker_through_repeated_cancellation_and_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
    cancel_close: bool,
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"payload")
    metadata = await adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
    gate = Gate()
    failure = OSError("close failed")
    close_count = 0

    class Stream(io.BytesIO):
        def close(self) -> None:
            nonlocal close_count
            close_count += 1
            gate.wait()
            if close_fails:
                raise failure
            super().close()

    stream = Stream(b"payload")

    def open_sync(key: str) -> tuple[AssetMetadataInfo, BinaryIO]:
        return metadata, stream

    monkeypatch.setattr(adapter, "_open_sync", open_sync)
    opened = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    task = asyncio.create_task(opened.aclose())
    try:
        await asyncio.wait_for(gate.started.wait(), 5)
        if cancel_close:
            task.cancel("first cancellation")
            await asyncio.sleep(0)
            task.cancel("second cancellation")
            await asyncio.sleep(0)
            assert not task.done()
        gate.release.set()
        if cancel_close:
            with pytest.raises(asyncio.CancelledError) as cancellation:
                await asyncio.wait_for(task, 5)
            assert cancellation.value.args == ("first cancellation",)
        elif close_fails:
            with pytest.raises(AssetStorageError) as error:
                await task
            assert error.value.__cause__ is failure
            assert error.value.operation == "read"
        else:
            await task
        assert stream.closed is not close_fails
        await opened.aclose()
        assert close_count == 1
    finally:
        gate.release.set()
        await asyncio.gather(task, return_exceptions=True)
        io.BytesIO.close(stream)


@pytest.mark.parametrize("corruption", ["json", "key", "size"])
async def test_invalid_metadata_keeps_error_and_releases_key(
    tmp_path: Path, corruption: str
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"payload")
    digest = hashlib.sha256(b"asset.bin").hexdigest()
    sidecar = tmp_path / ".asset_storage" / "metadata" / f"{digest}.json"
    if corruption == "json":
        sidecar.write_text("[", encoding="utf-8")
    else:
        fields = json.loads(sidecar.read_text(encoding="utf-8"))
        fields["object_key" if corruption == "key" else "size_bytes"] = "invalid"
        sidecar.write_text(json.dumps(fields), encoding="utf-8")
    with pytest.raises(AssetStorageError) as error:
        await adapter.read_asset(ReadAssetCommand("asset.bin"))
    assert error.value.kind is AssetStorageErrorKind.DATA_INTEGRITY
    assert error.value.object_key == "asset.bin"
    assert len(adapter._locks) == 0


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing contract")
@pytest.mark.parametrize("failing_step", ["publish", "cleanup"])
async def test_failed_windows_replacement_restores_body_and_metadata_with_reader_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    adapter = adapter_at(tmp_path)
    await store(adapter, "asset.bin", b"original")
    before = await adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
    opened = await adapter.read_asset(ReadAssetCommand("asset.bin"))
    replace, unlink = os.replace, Path.unlink
    data_path = tmp_path / "asset.bin"
    failure = OSError("replacement failed")
    failed = False

    def replace_file(source: Path, destination: Path) -> None:
        nonlocal failed
        if (
            failing_step == "publish"
            and source.suffix == ".tmp"
            and destination == data_path
            and not data_path.exists()
        ):
            failed = True
            raise failure
        replace(source, destination)

    def unlink_file(path: Path, missing_ok: bool = False) -> None:
        nonlocal failed
        if failing_step == "cleanup" and path.suffix == ".old":
            failed = True
            raise failure
        unlink(path, missing_ok=missing_ok)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(Local.os, "replace", replace_file)
            patch.setattr(Path, "unlink", unlink_file)
            with pytest.raises(AssetStorageError) as error:
                await store(adapter, "asset.bin", b"replacement")
        assert failed and error.value.__cause__ is failure
        assert (
            await adapter.get_asset_metadata(GetAssetMetadataCommand("asset.bin"))
            == before
        )
        assert await opened.read() == b"original"
        async with await adapter.read_asset(ReadAssetCommand("asset.bin")) as current:
            assert await current.read() == b"original"
        assert not list(tmp_path.rglob("*.old"))
        assert not list(tmp_path.rglob("*.tmp"))
    finally:
        await opened.aclose()


@pytest.mark.parametrize("failing_step", ["descriptor", "stream"])
async def test_windows_open_failure_closes_owned_native_handle_or_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing_step: str
) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows native handle ownership")
    path = tmp_path / "asset.bin"
    path.write_bytes(b"payload")
    failure = OSError("conversion failed")
    handles: list[int] = []
    descriptors: list[int] = []
    convert = Local.msvcrt.open_osfhandle
    close = Local._winapi.CloseHandle

    def convert_handle(handle: int, flags: int) -> int:
        if failing_step == "descriptor":
            raise failure
        descriptor = convert(handle, flags)
        descriptors.append(descriptor)
        return descriptor

    def close_handle(handle: int) -> None:
        handles.append(handle)
        close(handle)

    def fail_stream(descriptor: int, mode: str) -> BinaryIO:
        raise failure

    with monkeypatch.context() as patch:
        patch.setattr(Local.msvcrt, "open_osfhandle", convert_handle)
        patch.setattr(Local._winapi, "CloseHandle", close_handle)
        patch.setattr(Local.os, "fdopen", fail_stream)
        with pytest.raises(OSError) as error:
            Local._open_binary(path)
    assert error.value is failure
    if failing_step == "descriptor":
        assert len(handles) == 1 and not descriptors
    else:
        assert len(descriptors) == 1 and not handles
        with pytest.raises(OSError):
            os.fstat(descriptors[0])
    path.unlink()
