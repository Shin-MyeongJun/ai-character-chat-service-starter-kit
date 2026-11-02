"""Cancellation ownership with real asyncio tasks/threads and offline doubles."""

import asyncio
import io
import threading
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ReadTimeoutError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.modules.asset_storage import types as StorageTypes
from app.modules.asset_storage.adapters.s3_storage.adapter import S3StorageAdapter
from app.modules.content.character import types as Types
from app.modules.content.character.service.workflow.media import (
    CharacterMediaWorkflow,
    _settle_storage,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["upload", "cleanup"])
@pytest.mark.parametrize("provider_fails", [False, True])
@pytest.mark.parametrize("cancel_count", [1, 3])
async def test_workflow_keeps_transaction_until_provider_settles_then_cancels(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    provider_fails: bool,
    cancel_count: int,
) -> None:
    events: list[str] = []
    started, release = asyncio.Event(), asyncio.Event()

    def committed(session: Session) -> None:
        events.append("commit")

    def rolled_back(session: Session) -> None:
        events.append("rollback")

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            event.listen(session.sync_session, "after_commit", committed)
            event.listen(session.sync_session, "after_rollback", rolled_back)
            yield session

    info = Types.CharacterMediaInfo(
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        "s3",
        "test",
        "asset.bin",
        "image/png",
        7,
        "test.png",
        "portrait",
        "digest",
        "pending",
        None,
        datetime.now(UTC),
    )
    storage = MagicMock()
    workflow = CharacterMediaWorkflow(
        sessions, storage, storage_kind="s3", storage_id="test"
    )
    monkeypatch.setattr(workflow, "reserve_upload", AsyncMock(return_value=info))
    monkeypatch.setattr(workflow, "lock_upload", AsyncMock(return_value=info))
    monkeypatch.setattr(workflow, "prepare_cleanup", AsyncMock(return_value=info))
    monkeypatch.setattr(workflow, "lock_cleanup", AsyncMock(return_value=info))
    complete_upload, complete_cleanup = AsyncMock(), AsyncMock()
    monkeypatch.setattr(workflow, "complete_upload", complete_upload)
    monkeypatch.setattr(workflow, "complete_cleanup", complete_cleanup)

    async def store(
        command: StorageTypes.StoreAssetCommand,
    ) -> StorageTypes.StoredAssetInfo:
        started.set()
        await release.wait()
        events.append("provider-settled")
        if provider_fails:
            raise ValueError("provider failed after cancellation")
        return StorageTypes.StoredAssetInfo(
            StorageTypes.StorageKind.S3, "test", "asset.bin", 7, "image/png"
        )

    async def delete(command: StorageTypes.DeleteAssetCommand) -> None:
        await store(
            StorageTypes.StoreAssetCommand(
                "asset.bin", io.BytesIO(b"payload"), 7, "image/png"
            )
        )

    storage.store_asset = AsyncMock(side_effect=store)
    storage.delete_asset = AsyncMock(side_effect=delete)
    with io.BytesIO(b"payload") as content:
        task: (
            asyncio.Task[Types.CharacterMediaInfo]
            | asyncio.Task[Types.CleanupCharacterMediaInfo]
        )
        if operation == "upload":
            task = asyncio.create_task(
                workflow.upload_character_media(
                    Types.UploadCharacterMediaCommand(
                        info.character_id,
                        info.owner_id,
                        info.request_id,
                        content,
                        "image/png",
                        "test.png",
                        "portrait",
                    )
                )
            )
        else:
            task = asyncio.create_task(
                workflow.cleanup_character_media(
                    Types.CleanupCharacterMediaCommand(info.id, datetime.now(UTC))
                )
            )
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            for _ in range(cancel_count):
                task.cancel()
                await asyncio.sleep(0)
            assert not task.done()
            assert events == ["commit"]
            assert not content.closed
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
            assert events == ["commit", "provider-settled", "rollback"]
            complete_upload.assert_not_awaited()
            complete_cleanup.assert_not_awaited()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_uncancelled_provider_error_keeps_original_exception() -> None:
    failure = ValueError("provider failure")

    async def fail() -> None:
        raise failure

    with pytest.raises(ValueError) as caught:
        await _settle_storage(fail())
    assert caught.value is failure


class DelayedS3:
    def __init__(
        self,
        *,
        provider_fails: bool = False,
        invalid_metadata: bool = False,
        close_fails: bool = False,
    ) -> None:
        self.loop = asyncio.get_running_loop()
        self.get_started, self.close_started = asyncio.Event(), asyncio.Event()
        self.get_release, self.close_release = threading.Event(), threading.Event()
        self.provider_fails, self.invalid_metadata, self.close_fails = (
            provider_fails,
            invalid_metadata,
            close_fails,
        )
        self.close_count = 0
        self.closed = False
        self.thread_ids: list[int] = []

    def get_object(self, *, Bucket: str, Key: str) -> Mapping[str, object]:
        self.thread_ids.append(threading.get_ident())
        self.loop.call_soon_threadsafe(self.get_started.set)
        if not self.get_release.wait(timeout=5):
            raise TimeoutError("test get gate was not released")
        if self.provider_fails:
            raise ReadTimeoutError(endpoint_url="https://s3.invalid")
        return {
            "Body": self,
            "ContentLength": "invalid" if self.invalid_metadata else 7,
        }

    def read(self, size: int = -1) -> bytes:
        return b"payload" if size < 0 else b"payload"[:size]

    def close(self) -> None:
        self.thread_ids.append(threading.get_ident())
        self.close_count += 1
        self.loop.call_soon_threadsafe(self.close_started.set)
        if not self.close_release.wait(timeout=5):
            raise TimeoutError("test close gate was not released")
        if self.close_fails:
            raise OSError("close failure")
        self.closed = True

    def adapter(self) -> S3StorageAdapter:
        client = MagicMock()
        client.get_object.side_effect = self.get_object
        return S3StorageAdapter(
            StorageTypes.S3StorageSettings("test", "bucket", "ap-northeast-2"),
            client=client,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_metadata", [False, True])
@pytest.mark.parametrize("close_fails", [False, True])
async def test_cancelled_get_owns_late_body_and_waits_through_repeated_close_cancellation(
    invalid_metadata: bool,
    close_fails: bool,
) -> None:
    backend = DelayedS3(invalid_metadata=invalid_metadata, close_fails=close_fails)
    task = asyncio.create_task(
        backend.adapter().read_asset(StorageTypes.ReadAssetCommand("asset.bin"))
    )
    try:
        await asyncio.wait_for(backend.get_started.wait(), timeout=5)
        task.cancel("first cancellation")
        await asyncio.sleep(0)
        task.cancel("second cancellation")
        await asyncio.sleep(0)
        assert not task.done() and backend.close_count == 0
        backend.get_release.set()
        await asyncio.wait_for(backend.close_started.wait(), timeout=5)
        task.cancel("cancellation during close")
        await asyncio.sleep(0)
        assert not task.done()
        backend.close_release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await asyncio.wait_for(task, timeout=5)
        assert caught.value.args == ("first cancellation",)
        assert backend.close_count == 1 and backend.closed is not close_fails
        assert all(
            thread_id != threading.get_ident() for thread_id in backend.thread_ids
        )
    finally:
        backend.get_release.set()
        backend.close_release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_get_failure_is_consumed_without_replacing_cancellation() -> (
    None
):
    backend = DelayedS3(provider_fails=True)
    task = asyncio.create_task(
        backend.adapter().read_asset(StorageTypes.ReadAssetCommand("asset.bin"))
    )
    try:
        await asyncio.wait_for(backend.get_started.wait(), timeout=5)
        task.cancel("caller stopped")
        await asyncio.sleep(0)
        backend.get_release.set()
        with pytest.raises(asyncio.CancelledError, match="caller stopped"):
            await asyncio.wait_for(task, timeout=5)
        assert backend.close_count == 0
    finally:
        backend.get_release.set()
        backend.close_release.set()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_normal_get_transfers_reader_and_client_lifetime_to_existing_owners() -> (
    None
):
    backend = DelayedS3()
    backend.get_release.set()
    backend.close_release.set()
    opened = await backend.adapter().read_asset(
        StorageTypes.ReadAssetCommand("asset.bin")
    )
    assert not backend.closed
    assert await opened.read(3) == b"pay"
    await opened.aclose()
    await opened.aclose()
    assert backend.closed and backend.close_count == 1
