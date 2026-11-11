"""Durable private image uploads, imports, readers and explicit garbage collection."""

import asyncio
import hashlib
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast
from uuid import UUID

from app.core.storage_io import settle_storage_operation
from app.db.transaction import use_case_transaction
from app.db.types import SessionFactory
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.asset_storage.service import AssetStorageService
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.product import types as Types
from app.modules.content.product.mapper.file_versions import FileStorageInfo
from app.modules.content.product.service.command import (
    file_versions as FileVersionsCommandService,
)

MAX_PRODUCT_FILE_BYTES = 32 * 1024 * 1024
PRODUCT_IMAGE_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
_CHUNK_BYTES = 64 * 1024
State = Types.ProductFileVersionState


def _fingerprint_image(
    command: Types.UploadProductFileVersionCommand,
) -> tuple[int, str]:
    if command.content_type not in PRODUCT_IMAGE_CONTENT_TYPES:
        raise ValueError("Unsupported image content type.")
    filename = command.original_filename
    if (
        not filename.strip()
        or len(filename) > 255
        or any(character in "/\\" or ord(character) < 32 for character in filename)
    ):
        raise ValueError("Use an original filename without a path.")
    digest = hashlib.sha256()
    size_bytes = 0
    command.content.seek(0)
    while chunk := command.content.read(_CHUNK_BYTES):
        size_bytes += len(chunk)
        if size_bytes > MAX_PRODUCT_FILE_BYTES:
            raise ValueError("Image exceeds 32 MiB.")
        digest.update(chunk)
    command.content.seek(0)
    if not size_bytes:
        raise ValueError("Empty image.")
    return size_bytes, digest.hexdigest()


class ProductFileVersionWorkflow:
    def __init__(
        self,
        session_factory: SessionFactory,
        storage: AssetStorageService,
        character_media: CharacterMediaService,
        *,
        storage_kind: str,
        storage_id: str,
        read_storages: dict[tuple[str, str], AssetStorageService] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.character_media = character_media
        self.storage_kind = storage_kind
        self.storage_id = storage_id
        self.storages = {**(read_storages or {}), (storage_kind, storage_id): storage}

    async def upload_product_file_version(
        self, command: Types.UploadProductFileVersionCommand
    ) -> Types.ProductFileVersionInfo:
        """Read and rewind the caller's stream. The caller retains stream ownership."""
        return await self._upload_file_version(command, source_media_id=None)

    async def import_product_file_version(
        self, command: Types.ImportProductFileVersionCommand
    ) -> Types.ProductFileVersionInfo:
        async with self.session_factory() as session, use_case_transaction(session):
            previous = await FileVersionsCommandService._find_import_request(
                session, command
            )
        if previous is not None:
            return previous

        with SpooledTemporaryFile(max_size=1024 * 1024) as spool:
            source, opened = await self.character_media.open_owned_character_media(
                CharacterTypes.ReadCharacterMediaCommand(
                    media_id=command.media_id, owner_id=command.owner_id
                )
            )
            async with opened:
                if source.content_type not in PRODUCT_IMAGE_CONTENT_TYPES or not (
                    0 < source.size_bytes <= MAX_PRODUCT_FILE_BYTES
                ):
                    raise ValueError("Source is not a supported image.")
                _verify_asset_metadata(opened, source.content_type, source.size_bytes)
                size_bytes = 0
                digest = hashlib.sha256()
                while chunk := await opened.read(_CHUNK_BYTES):
                    size_bytes += len(chunk)
                    if size_bytes > source.size_bytes:
                        break
                    digest.update(chunk)
                    spool.write(chunk)
                if (
                    size_bytes != source.size_bytes
                    or digest.hexdigest() != source.sha256
                ):
                    raise _asset_integrity_error(opened.metadata.object_key)
            return await self._upload_file_version(
                Types.UploadProductFileVersionCommand(
                    product_id=command.product_id,
                    owner_id=command.owner_id,
                    request_id=command.request_id,
                    # The binary spool implements the BinaryIO methods used here.
                    content=cast(BinaryIO, spool),
                    content_type=source.content_type,
                    original_filename=source.original_filename,
                ),
                source_media_id=command.media_id,
            )

    async def read_owned_product_file_version(
        self, command: Types.ReadOwnedProductFileVersionCommand
    ) -> AssetStorageTypes.AssetReadInfo:
        async with self.session_factory() as session, use_case_transaction(session):
            info = await FileVersionsCommandService._get_owned_ready_file_version(
                session, command
            )
        return await self._open_file_version(info)

    async def read_referenced_product_file_version(
        self, command: Types.ProductFileReferenceCommand
    ) -> AssetStorageTypes.AssetReadInfo:
        """Trusted callers authorize the occurrence before opening its retained file."""
        async with self.session_factory() as session, use_case_transaction(session):
            info = await FileVersionsCommandService._get_referenced_file_version(
                session, command
            )
        return await self._open_file_version(info)

    async def cleanup_product_file_version(
        self, command: Types.GetProductFileVersionCommand
    ) -> Types.CleanupProductFileVersionInfo:
        async with self.session_factory() as session, use_case_transaction(session):
            outcome = await FileVersionsCommandService._prepare_file_cleanup(
                session, command
            )
            if isinstance(outcome, Types.CleanupProductFileVersionInfo):
                return outcome
        async with self.session_factory() as session, use_case_transaction(session):
            info = await FileVersionsCommandService._lock_file_cleanup(session, command)
            if info is None:
                return Types.CleanupProductFileVersionInfo(False, "absent_or_deleted")
            await settle_storage_operation(
                self._storage_for_file(info).delete_asset(
                    AssetStorageTypes.DeleteAssetCommand(info.object_key)
                )
            )
            await FileVersionsCommandService._complete_file_cleanup(session, command)
        return Types.CleanupProductFileVersionInfo(True, "deleted")

    async def _upload_file_version(
        self,
        command: Types.UploadProductFileVersionCommand,
        *,
        source_media_id: UUID | None,
    ) -> Types.ProductFileVersionInfo:
        size_bytes, sha256 = await settle_storage_operation(
            asyncio.to_thread(_fingerprint_image, command)
        )
        async with self.session_factory() as session, use_case_transaction(session):
            reservation = await FileVersionsCommandService._reserve_file_version(
                session,
                command,
                source_media_id=source_media_id,
                size_bytes=size_bytes,
                sha256=sha256,
                storage_kind=self.storage_kind,
                storage_id=self.storage_id,
            )
        async with self.session_factory() as session, use_case_transaction(session):
            info = await FileVersionsCommandService._lock_owned_file_version(
                session,
                Types.ReadOwnedProductFileVersionCommand(
                    product_id=command.product_id,
                    file_version_id=reservation.file.file_version_id,
                    owner_id=command.owner_id,
                ),
            )
            if info.file.state != State.PENDING:
                return info.file
            stored = await settle_storage_operation(
                self._storage_for_file(info).store_asset(
                    AssetStorageTypes.StoreAssetCommand(
                        info.object_key,
                        command.content,
                        info.file.size_bytes,
                        info.file.content_type,
                    )
                )
            )
            return await FileVersionsCommandService._complete_file_upload(
                session, info, stored
            )

    def _storage_for_file(self, info: FileStorageInfo) -> AssetStorageService:
        try:
            return self.storages[(info.storage_kind, info.storage_id)]
        except KeyError as exc:
            raise AssetStorageTypes.AssetStorageConfigurationError(
                "The recorded product image storage is not configured."
            ) from exc

    async def _open_file_version(
        self, info: FileStorageInfo
    ) -> AssetStorageTypes.AssetReadInfo:
        opened = await self._storage_for_file(info).read_asset(
            AssetStorageTypes.ReadAssetCommand(info.object_key)
        )
        try:
            _verify_asset_metadata(opened, info.file.content_type, info.file.size_bytes)
        except AssetStorageTypes.AssetStorageError:
            async with opened:
                raise
        return opened


def _verify_asset_metadata(
    opened: AssetStorageTypes.AssetReadInfo, content_type: str, size_bytes: int
) -> None:
    if (opened.metadata.content_type, opened.metadata.size_bytes) != (
        content_type,
        size_bytes,
    ):
        raise _asset_integrity_error(opened.metadata.object_key)


def _asset_integrity_error(object_key: str) -> AssetStorageTypes.AssetStorageError:
    return AssetStorageTypes.AssetStorageError(
        "Stored image differs from its recorded metadata.",
        kind=AssetStorageTypes.AssetStorageErrorKind.DATA_INTEGRITY,
        operation="read",
        object_key=object_key,
    )
