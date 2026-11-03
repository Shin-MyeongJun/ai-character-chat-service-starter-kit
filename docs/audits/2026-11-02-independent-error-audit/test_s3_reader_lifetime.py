"""HTTP response cancellation with real worker threads and a gated S3 body double."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.response import StreamingBody

from app.http.media import MediaStreamingResponse
from app.modules.asset_storage.adapters.s3_storage.adapter import S3StorageAdapter
from app.modules.asset_storage.types import ReadAssetCommand, S3StorageSettings


@pytest.mark.asyncio
@pytest.mark.parametrize("repeated", [True, False])
async def test_http_repeated_cancel_must_still_close_s3_body(repeated):
    loop = asyncio.get_running_loop()
    original_executor = loop._default_executor
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    started, finished, close_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release = threading.Event()
    close_calls = 0

    class RawStream(io.BytesIO):
        def read(self, size=-1):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise RuntimeError("audit read gate timed out")
            loop.call_soon_threadsafe(finished.set)
            return super().read(size)

        def close(self):
            nonlocal close_calls
            close_calls += 1
            super().close()

    raw = RawStream()
    body = StreamingBody(raw, 0)
    client = SimpleNamespace(get_object=lambda **_: {"Body": body, "ContentLength": 0})
    adapter = S3StorageAdapter(
        S3StorageSettings(storage_id="audit", bucket="synthetic", region="synthetic"),
        client=client,
    )
    task = None
    try:
        opened = await adapter.read_asset(ReadAssetCommand("audit-key"))
        actual_close = opened._reader.aclose

        async def observed_close():
            close_entered.set()
            await actual_close()

        opened._reader.aclose = observed_close
        response = MediaStreamingResponse(opened)
        task = asyncio.create_task(response(
            {"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), AsyncMock()
        ))
        await asyncio.wait_for(started.wait(), 5)
        task.cancel("first")
        await asyncio.wait_for(close_entered.wait(), 5)
        # The only executor thread still owns the gated read. The production
        # to_thread(close) has queued before this task gets control again.
        assert executor._work_queue.qsize() == 1
        if repeated:
            task.cancel("second")
        else:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        await asyncio.wait_for(finished.wait(), 5)
        # A completed executor barrier proves the cancelled close was skipped.
        await asyncio.to_thread(lambda: None)
        await opened.aclose()
        print(f"OBSERVED s3_http repeated_cancel={repeated} read_finished=True reader_marked_closed={opened._closed} body_close_calls={close_calls} raw_stream_closed={raw.closed}")
        assert close_calls == 1, "HTTP cleanup cancellation permanently skipped S3 Body.close"
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        executor.shutdown(wait=True)
        loop._default_executor = original_executor
        # The audit itself releases its synthetic body even when the assertion fails.
        body.close()
