"""Upload fingerprint offload and stream lifetime with real worker threads."""

import asyncio
import hashlib
import io
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from tempfile import SpooledTemporaryFile
from types import TracebackType
from typing import BinaryIO, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.db.models.character_media import CharacterMedia
from app.http import media as Http
from app.modules.content.character import types as Types
from app.modules.content.character.service import media as MediaService
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow


@pytest.fixture
def workflow(monkeypatch: pytest.MonkeyPatch) -> CharacterMediaWorkflow:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            yield session

    monkeypatch.setattr(MediaService, "_get_owned_character", AsyncMock())
    for name in ("get_media_request", "create_media", "set_media_state"):
        monkeypatch.setattr(
            MediaService.MediaRepository, name, AsyncMock(return_value=None)
        )
    return CharacterMediaWorkflow(
        sessions, MagicMock(), storage_kind="test_local", storage_id="test"
    )


def upload_command(content: BinaryIO) -> Types.UploadCharacterMediaCommand:
    return Types.UploadCharacterMediaCommand(
        character_id=uuid4(),
        owner_id=uuid4(),
        request_id=uuid4(),
        content=content,
        content_type="image/png",
        original_filename="portrait.png",
        purpose="portrait",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("spool_limit", [1, 1024 * 1024])
async def test_fingerprint_preserves_digest_rewind_and_idempotency(
    workflow: CharacterMediaWorkflow,
    monkeypatch: pytest.MonkeyPatch,
    spool_limit: int,
) -> None:
    payload = b"\x00\xffbinary" * 20000  # Multiple 64 KiB reads.
    with SpooledTemporaryFile(max_size=spool_limit) as content:
        content.write(payload)  # Start at EOF, as the HTTP transport does.
        command = upload_command(cast(BinaryIO, content))
        async with workflow.sessions() as session:
            info = await workflow.reserve_upload(session, command)
            assert info.size_bytes == len(payload)
            assert info.sha256 == hashlib.sha256(payload).hexdigest()
            assert content.tell() == 0 and not content.closed
            ready = replace(info, state="ready")
            monkeypatch.setattr(
                MediaService.MediaRepository,
                "get_media_request",
                AsyncMock(return_value=CharacterMedia(**asdict(ready))),
            )
            assert await workflow.reserve_upload(session, command) == ready
            assert content.tell() == 0
            with io.BytesIO(b"different") as changed:
                with pytest.raises(ValueError, match="different media"):
                    await workflow.reserve_upload(
                        session, replace(command, content=changed)
                    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "payload", "message"),
    [
        ({"content_type": "text/plain"}, b"payload", "Unsupported"),
        ({"original_filename": "../file.png"}, b"payload", "filename"),
        ({"purpose": " "}, b"payload", "purpose"),
        ({}, b"", "Empty"),
        ({}, b"12345", "32 MiB"),
    ],
)
async def test_invalid_fingerprint_never_reserves_or_stores_media(
    workflow: CharacterMediaWorkflow,
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, str],
    payload: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(MediaService, "MAX_MEDIA_BYTES", 4)
    with io.BytesIO(payload) as content, pytest.raises(ValueError, match=message):
        async with workflow.sessions() as session:
            await workflow.reserve_upload(
                session, replace(upload_command(content), **changes)
            )
    MediaService._get_owned_character.assert_not_awaited()
    MediaService.MediaRepository.create_media.assert_not_awaited()
    workflow.storage.store_asset.assert_not_called()


class GatedUpload(SpooledTemporaryFile[bytes]):
    def __init__(self, *, block_at: str, worker_fails: bool) -> None:
        super().__init__(max_size=1)  # Exercise an actual rolled disk spool.
        self.loop = asyncio.get_running_loop()
        self.started = asyncio.Event()
        self.release = threading.Event()
        self.block_at = block_at
        self.worker_fails = worker_fails
        self.failure = OSError("fingerprint I/O failed")
        self.thread_ids: list[int] = []
        self.events: list[str] = []
        self.seek_count = 0

    def wait_for_release(self) -> None:
        self.events.append("worker-started")
        self.loop.call_soon_threadsafe(self.started.set)
        try:
            if not self.release.wait(timeout=5):
                raise TimeoutError("fingerprint gate was not released")
            assert not self.closed
            if self.worker_fails:
                raise self.failure
        finally:
            self.events.append("worker-released")

    def read(self, size: int = -1) -> bytes:
        self.thread_ids.append(threading.get_ident())
        if self.block_at == "read" and not self.started.is_set():
            self.wait_for_release()
        return super().read(size)

    def seek(self, offset: int, whence: int = 0) -> int:
        self.thread_ids.append(threading.get_ident())
        self.seek_count += 1
        if self.block_at == "rewind" and self.seek_count == 2:
            self.wait_for_release()
        return super().seek(offset, whence)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        super().__exit__(exc_type, exc_value, traceback)
        self.events.append("closed")


@pytest.mark.asyncio
@pytest.mark.parametrize("block_at", ["read", "rewind"])
@pytest.mark.parametrize("worker_fails", [False, True])
@pytest.mark.parametrize("cancel_count", [1, 3])
async def test_cancelled_http_upload_keeps_file_until_fingerprint_worker_finishes(
    workflow: CharacterMediaWorkflow,
    monkeypatch: pytest.MonkeyPatch,
    block_at: str,
    worker_fails: bool,
    cancel_count: int,
) -> None:
    content = GatedUpload(block_at=block_at, worker_fails=worker_fails)
    monkeypatch.setattr(Http, "SpooledTemporaryFile", lambda **_: content)
    request = Request(
        {"type": "http"},
        AsyncMock(
            return_value={
                "type": "http.request",
                "body": b"payload",
                "more_body": False,
            }
        ),
    )
    task = asyncio.create_task(
        Http.upload_character_media(
            character_id=uuid4(),
            request=request,
            owner=uuid4(),
            service=workflow,
            idempotency_key=uuid4(),
            content_type="image/png",
            x_filename="portrait.png",
            x_media_purpose="portrait",
        )
    )
    try:
        # The event loop must be free while a real worker blocks on file I/O.
        await asyncio.wait_for(content.started.wait(), timeout=2)
        assert content.thread_ids
        assert threading.get_ident() not in content.thread_ids
        for index in range(cancel_count):
            task.cancel(f"cancel-{index}")
            await asyncio.sleep(0)
            assert not task.done() and not content.closed
        content.release.set()
        with pytest.raises(asyncio.CancelledError, match="cancel-0"):
            await asyncio.wait_for(task, timeout=2)
        assert content.closed
        assert content.events == ["worker-started", "worker-released", "closed"]
        MediaService._get_owned_character.assert_not_awaited()
        MediaService.MediaRepository.create_media.assert_not_awaited()
        workflow.storage.store_asset.assert_not_called()
    finally:
        content.release.set()
        await asyncio.gather(task, return_exceptions=True)
        content.close()


@pytest.mark.asyncio
async def test_uncancelled_file_failure_preserves_exception_and_caller_ownership(
    workflow: CharacterMediaWorkflow,
) -> None:
    with GatedUpload(block_at="read", worker_fails=True) as content:
        content.write(b"payload")
        content.release.set()
        async with workflow.sessions() as session:
            with pytest.raises(OSError) as caught:
                await workflow.reserve_upload(
                    session, upload_command(cast(BinaryIO, content))
                )
        assert caught.value is content.failure
        assert not content.closed
