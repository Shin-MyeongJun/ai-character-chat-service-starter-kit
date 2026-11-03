"""Offline lifetime checks with real workers and installed botocore StreamingBody."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import AsyncIterator, Callable, Coroutine
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import ParamSpec, TypeVar
from unittest.mock import AsyncMock, Mock

import pytest
from botocore.exceptions import ReadTimeoutError
from botocore.response import StreamingBody
from uvicorn import Config, Server

from app.http.media import MediaStreamingResponse
from app.modules.asset_storage.adapters.s3_storage.adapter import S3StorageAdapter
from app.modules.asset_storage.adapters.test_local_storage import adapter as Local
from app.modules.asset_storage.types import (
    AssetMetadataInfo,
    AssetReadInfo,
    AssetStorageError,
    AssetStorageErrorKind,
    ReadAssetCommand,
    S3StorageSettings,
    StorageKind,
)

pytestmark = pytest.mark.asyncio
P = ParamSpec("P")
T = TypeVar("T")


async def checkpoint() -> None:
    """One loop handoff, without timing-dependent sleeps."""
    future = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


async def reached(event: asyncio.Event) -> None:
    await asyncio.wait_for(event.wait(), 5)


class Gate:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.started, self.finished = asyncio.Event(), asyncio.Event()
        self.release = threading.Event()
        self.release.set()

    def wait(self) -> None:
        self.loop.call_soon_threadsafe(self.started.set)
        if not self.release.wait(10):
            raise TimeoutError("synthetic worker gate was not released")

    def finish(self) -> None:
        self.loop.call_soon_threadsafe(self.finished.set)


class ObservedExecutor(ThreadPoolExecutor):
    def __init__(self, workers: int) -> None:
        super().__init__(max_workers=workers)
        self.submitted: list[asyncio.Event] = [asyncio.Event() for _ in range(32)]
        self.count = 0

    def submit(
        self, fn: Callable[P, T], /, *args: P.args, **kwargs: P.kwargs
    ) -> Future[T]:
        future = super().submit(fn, *args, **kwargs)
        self.submitted[self.count].set()
        self.count += 1
        return future


class RawStream(io.BytesIO):
    def __init__(self) -> None:
        super().__init__(b"payload")
        self.read_gate, self.close_gate = Gate(), Gate()
        self.read_error: Exception | None = None
        self.close_error: Exception | None = None
        self.close_calls = 0
        self.active_read = False
        self.overlap = False
        self.thread_ids: list[int] = []
        self.read_sizes: list[int | None] = []
        self.order: list[str] = []

    def read(self, size: int | None = -1) -> bytes:
        self.thread_ids.append(threading.get_ident())
        self.read_sizes.append(size)
        self.active_read = True
        self.order.append("read:start")
        try:
            self.read_gate.wait()
            if self.read_error is not None:
                raise self.read_error
            return super().read(size)
        finally:
            self.active_read = False
            self.order.append("read:end")
            self.read_gate.finish()

    def close(self) -> None:
        self.thread_ids.append(threading.get_ident())
        self.overlap |= self.active_read
        self.close_calls += 1
        self.order.append("close:start")
        try:
            self.close_gate.wait()
            if self.close_error is not None:
                raise self.close_error
            super().close()
        finally:
            self.order.append("close:end")
            self.close_gate.finish()


@dataclass
class ReaderCase:
    opened: AssetReadInfo
    raw: RawStream
    executor: ObservedExecutor
    adapter: S3StorageAdapter
    client: Mock
    tasks: list[asyncio.Task[None] | asyncio.Task[bytes]] = field(default_factory=list)

    def start(self, operation: Coroutine[object, object, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(operation)
        self.tasks.append(task)
        return task

    def read(self) -> asyncio.Task[bytes]:
        task = asyncio.create_task(self.opened.read(64 * 1024))
        self.tasks.append(task)
        return task

    async def settled(self, *, closed: bool = True) -> None:
        await reached(self.raw.close_gate.finished)
        await asyncio.to_thread(lambda: None)  # Executor completion barrier.
        assert all(task.done() for task in self.tasks)
        assert self.opened._close_task is not None
        assert self.opened._close_task.done()
        assert not getattr(self.opened._reader, "_reads")
        assert self.raw.closed is closed
        assert self.raw.close_calls == 1 and not self.raw.overlap
        assert all(ident != threading.get_ident() for ident in self.raw.thread_ids)
        print(
            f"OBSERVED read_finished={self.raw.read_gate.finished.is_set()} "
            f"close_finished={self.raw.close_gate.finished.is_set()} "
            f"close_calls={self.raw.close_calls} raw_closed={self.raw.closed} "
            "pending_reads=0 close_task_done=True caller_tasks_done=True overlap=False"
        )


@asynccontextmanager
async def s3_reader(workers: int = 1) -> AsyncIterator[ReaderCase]:
    loop = asyncio.get_running_loop()
    previous = getattr(loop, "_default_executor")
    previous_handler = loop.get_exception_handler()
    unhandled: list[dict[str, object]] = []

    def record_unhandled(
        event_loop: asyncio.AbstractEventLoop, context: dict[str, object]
    ) -> None:
        unhandled.append(context)

    loop.set_exception_handler(record_unhandled)
    executor = ObservedExecutor(workers)
    loop.set_default_executor(executor)
    raw = RawStream()
    client = Mock()
    client.get_object.return_value = {
        "Body": StreamingBody(raw, 7),
        "ContentLength": 7,
    }
    adapter = S3StorageAdapter(
        S3StorageSettings("test", "synthetic", "synthetic"), client=client
    )
    case: ReaderCase | None = None
    try:
        opened = await adapter.read_asset(ReadAssetCommand("asset.bin"))
        case = ReaderCase(opened, raw, executor, adapter, client)
        yield case
    finally:
        raw.read_gate.release.set()
        raw.close_gate.release.set()
        if case is not None:
            await asyncio.gather(*case.tasks, return_exceptions=True)
            try:
                await case.opened.aclose()
            except Exception:
                pass  # Failure injection is asserted by the test itself.
        await asyncio.to_thread(lambda: None)
        executor.shutdown(wait=True)
        setattr(loop, "_default_executor", previous)
        loop.set_exception_handler(previous_handler)
        io.BytesIO.close(raw)  # Release even a deliberately failed physical close.
        assert all(not thread.is_alive() for thread in executor._threads)
        assert not unhandled
        print(f"RECLAIMED workers={len(executor._threads)} alive=0 unhandled=0")


async def test_normal_stream_and_idempotent_close_preserve_owners() -> None:
    async with s3_reader() as case:
        assert not case.raw.closed
        assert await case.opened.read(3) == b"pay"
        assert await case.opened.read(3) == b"loa"
        assert await case.opened.read(3) == b"d"
        assert await case.opened.read(3) == b""
        await case.opened.aclose()
        await case.opened.aclose()
        await case.adapter.aclose()
        case.client.close.assert_not_called()
        with pytest.raises(ValueError, match="closed"):
            await case.opened.read(1)
        await case.settled()
        assert case.raw.read_sizes == [3, 3, 3, 3]


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("cancel_count", [0, 1, 3])
async def test_inflight_read_and_concurrent_close_are_owned_until_io_finishes(
    workers: int, cancel_count: int
) -> None:
    async with s3_reader(workers) as case:
        case.raw.read_gate.release.clear()
        read = case.read()
        await reached(case.raw.read_gate.started)
        if cancel_count:
            read.cancel("read cancelled")
            with pytest.raises(asyncio.CancelledError, match="read cancelled"):
                await read
        first = case.start(case.opened.aclose())
        await checkpoint()  # Close drains the read on the loop before submission.
        assert not case.executor.submitted[2].is_set()
        second = case.start(case.opened.aclose())
        await checkpoint()  # Both close coroutines have entered before cancellation.
        for index in range(cancel_count):
            first.cancel(f"close {index}")
            second.cancel(f"concurrent {index}")
            await checkpoint()
        assert not first.done() and not second.done()
        assert case.raw.close_calls == 0
        assert not case.raw.read_gate.finished.is_set()
        with pytest.raises(ValueError, match="closed"):
            await case.opened.read(1)
        case.raw.read_gate.release.set()
        await reached(case.raw.read_gate.finished)
        for task, message in ((first, "close 0"), (second, "concurrent 0")):
            if cancel_count:
                with pytest.raises(asyncio.CancelledError, match=message):
                    await asyncio.wait_for(task, 5)
            else:
                await asyncio.wait_for(task, 5)
        if not cancel_count:
            assert await read == b"payload"
        await case.settled()
        assert case.raw.order.index("read:end") < case.raw.order.index("close:start")


@pytest.mark.parametrize("cancel_count", [1, 3])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_cancellation_during_actual_close_retrieves_failure_and_first_cancel(
    cancel_count: int, close_fails: bool
) -> None:
    async with s3_reader() as case:
        failure = ReadTimeoutError(endpoint_url="https://s3.invalid")
        case.raw.close_error = failure if close_fails else None
        case.raw.close_gate.release.clear()
        task = case.start(case.opened.aclose())
        await reached(case.raw.close_gate.started)
        for index in range(cancel_count):
            task.cancel(f"cancel {index}")
            await checkpoint()
        assert not task.done() and not case.raw.close_gate.finished.is_set()
        case.raw.close_gate.release.set()
        with pytest.raises(asyncio.CancelledError, match="cancel 0"):
            await asyncio.wait_for(task, 5)
        await case.opened.aclose()
        await case.settled(closed=not close_fails)
        close_task = case.opened._close_task
        assert close_task is not None
        error = close_task.exception()
        if close_fails:
            assert isinstance(error, AssetStorageError) and error.__cause__ is failure
        else:
            assert error is None


@pytest.mark.parametrize("cancel_read", [False, True])
async def test_late_read_error_is_retrieved_and_physical_close_still_runs(
    cancel_read: bool,
) -> None:
    async with s3_reader(2) as case:
        failure = ReadTimeoutError(endpoint_url="https://s3.invalid")
        case.raw.read_error = failure
        case.raw.read_gate.release.clear()
        read = case.read()
        await reached(case.raw.read_gate.started)
        if cancel_read:
            read.cancel("read stopped")
            with pytest.raises(asyncio.CancelledError, match="read stopped"):
                await read
        close = case.start(case.opened.aclose())
        await checkpoint()
        assert not case.executor.submitted[2].is_set()
        case.raw.read_gate.release.set()
        if not cancel_read:
            with pytest.raises(AssetStorageError) as error:
                await read
            assert error.value.__cause__ is failure
        await close
        await case.settled()


@pytest.mark.parametrize("cancel_read", [False, True])
@pytest.mark.parametrize("read_fails", [False, True])
async def test_stalled_read_cleanup_leaves_second_worker_available(
    cancel_read: bool,
    read_fails: bool,
) -> None:
    async with s3_reader(2) as case:
        case.raw.read_gate.release.clear()
        if read_fails:
            case.raw.read_error = ReadTimeoutError(endpoint_url="https://s3.invalid")
        read = case.read()
        await reached(case.raw.read_gate.started)
        if cancel_read:
            read.cancel("read caller stopped")
            with pytest.raises(asyncio.CancelledError):
                await read
        close = case.start(case.opened.aclose())
        concurrent = case.start(case.opened.aclose())
        await checkpoint()
        for index in range(3):
            close.cancel(f"cleanup {index}")
            await checkpoint()
        assert not close.done() and not concurrent.done()
        assert case.raw.close_calls == 0
        assert case.executor.count == 2  # get + actual read; no lock-wait worker.
        assert (
            await asyncio.wait_for(asyncio.to_thread(lambda: "healthy"), 2) == "healthy"
        )
        assert not case.raw.read_gate.finished.is_set()
        with pytest.raises(ValueError, match="closed"):
            await case.opened.read(1)
        case.raw.read_gate.release.set()
        if not cancel_read:
            if read_fails:
                with pytest.raises(AssetStorageError):
                    await read
            else:
                assert await read == b"payload"
        with pytest.raises(asyncio.CancelledError, match="cleanup 0"):
            await close
        await concurrent
        await case.settled()


async def test_close_drains_read_admitted_before_worker_starts() -> None:
    async with s3_reader() as case:
        busy = Gate()
        busy.release.clear()
        worker = case.start(asyncio.to_thread(busy.wait))
        try:
            await reached(busy.started)
            read = case.read()
            await reached(
                case.executor.submitted[2]
            )  # Admitted read queued behind busy.
            close = case.start(case.opened.aclose())
            await checkpoint()
            assert case.raw.read_sizes == [] and case.raw.close_calls == 0
            assert case.executor.count == 3
            busy.release.set()
            await worker
            assert await asyncio.wait_for(read, 5) == b"payload"
            await asyncio.wait_for(close, 5)
            assert case.raw.order == [
                "read:start",
                "read:end",
                "close:start",
                "close:end",
            ]
            await case.settled()
        finally:
            busy.release.set()


async def test_close_failure_is_one_completed_attempt_for_all_concurrent_callers() -> (
    None
):
    async with s3_reader() as case:
        failure = ReadTimeoutError(endpoint_url="https://s3.invalid")
        case.raw.close_error = failure
        case.raw.close_gate.release.clear()
        first = case.start(case.opened.aclose())
        await reached(case.raw.close_gate.started)
        second = case.start(case.opened.aclose())
        await checkpoint()
        case.raw.close_gate.release.set()
        errors = await asyncio.gather(first, second, return_exceptions=True)
        assert errors[0] is errors[1]
        assert isinstance(errors[0], AssetStorageError)
        assert errors[0].__cause__ is failure
        await case.opened.aclose()
        await case.settled(closed=False)


@pytest.mark.parametrize("close_fails", [False, True])
async def test_queued_close_survives_repeated_cancel_with_unrelated_busy_worker(
    close_fails: bool,
) -> None:
    async with s3_reader() as case:
        busy = Gate()
        busy.release.clear()
        if close_fails:
            case.raw.close_error = OSError("queued close failed")
        worker = case.start(asyncio.to_thread(busy.wait))
        try:
            await reached(busy.started)
            close = case.start(case.opened.aclose())
            await reached(case.executor.submitted[2])
            for index in range(3):
                close.cancel(f"queued {index}")
                await checkpoint()
            assert not close.done() and case.raw.close_calls == 0
            assert case.opened._close_task is not None
            assert not case.opened._close_task.done()
            busy.release.set()
            await worker
            with pytest.raises(asyncio.CancelledError, match="queued 0"):
                await asyncio.wait_for(close, 5)
            await case.settled(closed=not close_fails)
            assert not case.raw.read_gate.started.is_set()
        finally:
            busy.release.set()


@pytest.mark.parametrize("spec", ["2.3", "2.4"])
@pytest.mark.parametrize("extra_cancel", [False, True])
async def test_http_disconnect_or_task_cancel_with_queued_close(
    spec: str, extra_cancel: bool
) -> None:
    async with s3_reader() as case:
        case.raw.read_gate.release.clear()

        async def receive() -> dict[str, str]:
            await case.raw.read_gate.started.wait()
            return {"type": "http.disconnect"}

        send = AsyncMock()
        response = case.start(
            MediaStreamingResponse(case.opened)(
                {"type": "http", "asgi": {"spec_version": spec}}, receive, send
            )
        )
        await reached(case.raw.read_gate.started)
        if spec == "2.4":
            response.cancel("first response cancellation")
        await checkpoint()
        await checkpoint()  # Disconnect/cancellation has entered shared cleanup.
        assert case.opened._close_task is not None
        assert not case.executor.submitted[2].is_set()
        assert case.raw.close_calls == 0 and not response.done()
        if extra_cancel:
            if spec == "2.3":
                # Installed Uvicorn code path, with an explicitly finite budget.
                server = Server(Config(app=AsyncMock(), timeout_graceful_shutdown=0))
                server.servers = []
                server.lifespan = Mock(shutdown=AsyncMock())
                server.server_state.tasks.add(response)
                await server.shutdown()
            else:
                response.cancel("second response cancellation")
            await checkpoint()
            response.cancel("third response cancellation")
            await checkpoint()
            assert not response.done()
        # Release physical I/O before joining cleanup: cancellation now waits for it.
        case.raw.read_gate.release.set()
        if spec == "2.4" or extra_cancel:
            with pytest.raises(asyncio.CancelledError) as error:
                await asyncio.wait_for(response, 5)
            if spec == "2.4":
                assert error.value.args == ("first response cancellation",)
        else:
            await asyncio.wait_for(response, 5)
        await case.opened.aclose()
        await case.settled()
        assert case.raw.read_sizes == [64 * 1024]


@pytest.mark.parametrize("primary", ["none", "read", "cancel", "send"])
@pytest.mark.parametrize("cancel_cleanup", [False, True])
async def test_http_original_failure_precedes_cleanup_error(
    primary: str, cancel_cleanup: bool
) -> None:
    async with s3_reader() as case:
        read_error = ReadTimeoutError(endpoint_url="https://read.invalid")
        close_error = ReadTimeoutError(endpoint_url="https://close.invalid")
        send_error = RuntimeError("send failed")
        case.raw.close_error = close_error
        if cancel_cleanup:
            case.raw.close_gate.release.clear()
        if primary == "read":
            case.raw.read_error = read_error
        if primary == "cancel":
            case.raw.read_gate.release.clear()
        send = AsyncMock(side_effect=send_error if primary == "send" else None)
        response = case.start(
            MediaStreamingResponse(case.opened)(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), send
            )
        )
        if primary == "cancel":
            await reached(case.raw.read_gate.started)
            response.cancel("original cancellation")
            await checkpoint()
            await checkpoint()
            assert case.opened._close_task is not None
            assert not case.executor.submitted[2].is_set()
            response.cancel("cleanup cancellation")
            case.raw.read_gate.release.set()
        if cancel_cleanup:
            await reached(case.raw.close_gate.started)
            response.cancel("late cleanup cancellation")
            await checkpoint()
            assert not response.done()
            case.raw.close_gate.release.set()
        with pytest.raises(
            (AssetStorageError, asyncio.CancelledError, RuntimeError)
        ) as error:
            await asyncio.wait_for(response, 5)
        if primary == "cancel":
            assert isinstance(error.value, asyncio.CancelledError)
            assert error.value.args == ("original cancellation",)
        elif primary == "none" and cancel_cleanup:
            assert isinstance(error.value, asyncio.CancelledError)
            assert error.value.args == ("late cleanup cancellation",)
        elif primary == "send":
            assert error.value is send_error
        else:
            assert isinstance(error.value, AssetStorageError)
            assert error.value.__cause__ is (
                read_error if primary == "read" else close_error
            )
        await case.settled(closed=False)


@pytest.mark.parametrize("backend", ["s3", "local"])
async def test_context_original_error_survives_cancelled_failing_close(
    backend: str,
) -> None:
    loop = asyncio.get_running_loop()
    previous = getattr(loop, "_default_executor")
    executor = ObservedExecutor(1)
    loop.set_default_executor(executor)
    raw = RawStream()
    raw.close_gate.release.clear()
    raw.close_error = OSError("close failed")
    original = RuntimeError("context failed")
    if backend == "local":
        reader = Local._LocalAssetReader(
            raw,
            lambda exc: AssetStorageError(
                str(exc),
                kind=AssetStorageErrorKind.PROVIDER,
                operation="read",
                object_key="asset.bin",
            ),
        )
        opened = AssetReadInfo(
            AssetMetadataInfo(
                StorageKind.TEST_LOCAL, "test", "asset.bin", 7, "test/data"
            ),
            reader,
        )
    else:
        client = Mock()
        client.get_object.return_value = {
            "Body": StreamingBody(raw, 7),
            "ContentLength": 7,
        }
        adapter = S3StorageAdapter(
            S3StorageSettings("test", "synthetic", "synthetic"), client=client
        )
        opened = await adapter.read_asset(ReadAssetCommand("asset.bin"))

    async def use_reader() -> None:
        async with opened:
            raise original

    task = asyncio.create_task(use_reader())
    concurrent: asyncio.Task[None] | None = None
    try:
        await reached(raw.close_gate.started)
        concurrent = asyncio.create_task(opened.aclose())
        await checkpoint()
        for index in range(3):
            task.cancel(f"late {index}")
            await checkpoint()
        assert not task.done() and not concurrent.done()
        raw.close_gate.release.set()
        with pytest.raises(RuntimeError) as error:
            await asyncio.wait_for(task, 5)
        assert error.value is original
        with pytest.raises((OSError, AssetStorageError)):
            await concurrent
        await opened.aclose()
        assert opened._close_task is not None and opened._close_task.done()
        assert raw.close_calls == 1 and not raw.closed
    finally:
        raw.close_gate.release.set()
        await asyncio.gather(
            task, *([concurrent] if concurrent else []), return_exceptions=True
        )
        await asyncio.to_thread(lambda: None)
        executor.shutdown(wait=True)
        setattr(loop, "_default_executor", previous)
        io.BytesIO.close(raw)
        assert all(not thread.is_alive() for thread in executor._threads)
        print(
            f"CONTEXT backend={backend} close_finished={raw.close_gate.finished.is_set()} "
            f"close_calls={raw.close_calls} workers_alive=0 caller_tasks_done=True"
        )
