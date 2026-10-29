"""Durable media I/O. Hold row locks until cancelled provider work settles."""

import asyncio
from collections.abc import Coroutine
from typing import TypeVar

from app.db.transaction import use_case_transaction
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.character import types as Types
from app.modules.content.character.service.media import CharacterMediaService

TStorageResult = TypeVar("TStorageResult")


# 취소를 기억하되 공급자 작업 종료까지 기다린다. 동기 SDK 스레드가 끝나기 전에 DB 잠금을 풀지 않기 위한 경계다.
async def _settle_storage(
    operation: Coroutine[object, object, TStorageResult],
) -> TStorageResult:
    # to_thread-backed providers can keep writing after cancellation. Keep the
    # DB lock until the provider settles so retry/GC cannot race that write.
    task = asyncio.create_task(operation)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        # Retrieve any provider exception while preserving caller cancellation.
        try:
            task.result()
        finally:
            raise asyncio.CancelledError
    return task.result()


class CharacterMediaWorkflow(CharacterMediaService):
    """Adds upload/cleanup execution to the authorized media operations."""

    async def upload_character_media(
        self, command: Types.UploadCharacterMediaCommand
    ) -> Types.CharacterMediaInfo:
        async with self.sessions() as session, use_case_transaction(session):
            info = await self.reserve_upload(session, command)
        async with self.sessions() as session, use_case_transaction(session):
            info = await self.lock_upload(
                session,
                Types.LockMediaUploadCommand(
                    info.id, command.character_id, command.owner_id
                ),
            )
            if info.state == "ready":
                return info
            stored = await _settle_storage(
                self._storage_for_media(info).store_asset(
                    AssetStorageTypes.StoreAssetCommand(
                        info.object_key,
                        command.content,
                        info.size_bytes,
                        command.content_type,
                    )
                )
            )
            return await self.complete_upload(
                session, Types.CompleteMediaUploadCommand(info, stored)
            )

    async def cleanup_character_media(
        self, command: Types.CleanupCharacterMediaCommand
    ) -> Types.CleanupCharacterMediaInfo:
        async with self.sessions() as session, use_case_transaction(session):
            result = await self.prepare_cleanup(session, command)
            if isinstance(result, Types.CleanupCharacterMediaInfo):
                return result
        async with self.sessions() as session, use_case_transaction(session):
            info = await self.lock_cleanup(session, command)
            if info is None:
                return Types.CleanupCharacterMediaInfo(False, "absent_or_deleted")
            await _settle_storage(
                self._storage_for_media(info).delete_asset(
                    AssetStorageTypes.DeleteAssetCommand(info.object_key)
                )
            )
            await self.complete_cleanup(session, command)
        return Types.CleanupCharacterMediaInfo(True, "deleted")
