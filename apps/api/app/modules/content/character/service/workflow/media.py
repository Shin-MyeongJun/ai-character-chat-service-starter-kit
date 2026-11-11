"""Durable media I/O. Hold row locks until cancelled provider work settles."""

from app.core.storage_io import settle_storage_operation as _settle_storage
from app.db.transaction import use_case_transaction
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.character import types as Types
from app.modules.content.character.service.media import CharacterMediaService


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
