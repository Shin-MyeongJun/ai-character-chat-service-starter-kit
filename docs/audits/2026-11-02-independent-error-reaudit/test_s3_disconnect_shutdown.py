"""ASGI 2.3 disconnect + installed Uvicorn shutdown; no network/S3 requests."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import io
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.response import StreamingBody
from uvicorn import Config, Server

from app.http.media import MediaStreamingResponse
from app.modules.asset_storage.adapters.s3_storage.adapter import S3StorageAdapter
from app.modules.asset_storage.types import ReadAssetCommand, S3StorageSettings


@pytest.mark.asyncio
@pytest.mark.parametrize('shutdown', [True, False])
async def test_asgi23_disconnect_and_server_shutdown_closes_body(shutdown):
    loop = asyncio.get_running_loop()
    previous = loop._default_executor
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    read_started, read_finished, close_entered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    release = threading.Event()
    closes = []

    class Raw(io.BytesIO):
        def read(self, size=-1):
            loop.call_soon_threadsafe(read_started.set)
            if not release.wait(8):
                raise RuntimeError('Audit gate timed out')
            loop.call_soon_threadsafe(read_finished.set)
            return super().read(size)

        def close(self):
            closes.append('close')
            super().close()

    raw = Raw(b'audit')
    body = StreamingBody(raw, 5)
    adapter = S3StorageAdapter(S3StorageSettings(storage_id='audit', bucket='synthetic', region='synthetic'),
                              client=SimpleNamespace(get_object=lambda **_: {'Body': body, 'ContentLength': 5}))
    task = None
    try:
        opened = await adapter.read_asset(ReadAssetCommand('audit'))
        actual_close = opened._reader.aclose

        async def observed_close():
            close_entered.set()
            await actual_close()

        opened._reader.aclose = observed_close

        async def receive():
            await read_started.wait()
            return {'type': 'http.disconnect'}

        task = asyncio.create_task(MediaStreamingResponse(opened)(
            {'type': 'http', 'asgi': {'spec_version': '2.3'}}, receive, AsyncMock()))
        await asyncio.wait_for(close_entered.wait(), 5)
        assert executor._work_queue.qsize() == 1
        if shutdown:
            server = Server(Config(app=AsyncMock(), timeout_graceful_shutdown=0, log_config=None))
            server.servers = []
            server.lifespan = SimpleNamespace(shutdown=AsyncMock())
            server.server_state.tasks.add(task)
            await server.shutdown()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            await task
        release.set()
        await asyncio.wait_for(read_finished.wait(), 5)
        await asyncio.to_thread(lambda: None)
        await opened.aclose()
        print(f'HTTP_ASGI23 disconnect=True uvicorn_shutdown={shutdown} close_calls={len(closes)} raw_closed={raw.closed} reader_marked_closed={opened._closed}')
        assert len(closes) == 1, 'Real server cancellation of disconnect cleanup loses Body.close'
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        executor.shutdown(wait=True)
        loop._default_executor = previous
        body.close()
