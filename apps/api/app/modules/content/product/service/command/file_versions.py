"""Product file version state changes and reference retention."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import (
    file_versions as FileVersionsPersistenceMapper,
)
from app.modules.content.product.mapper.file_versions import FileStorageInfo
from app.modules.content.product.repository import (
    file_versions as FileVersionsRepository,
)
from app.modules.content.product.service import query as QueryService

State = Types.ProductFileVersionState
_RETENTION = timedelta(hours=24)


async def _reserve_file_version(
    session: AsyncSession,
    command: Types.UploadProductFileVersionCommand,
    *,
    source_media_id: UUID | None,
    size_bytes: int,
    sha256: str,
    storage_kind: str,
    storage_id: str,
) -> FileStorageInfo:
    # Serialize creation under the product row before the request row exists.
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id, lock=True
        ),
    )
    info = FileVersionsPersistenceMapper.file_entity_to_storage_info(
        await FileVersionsRepository.get_file_request(
            session, command.product_id, command.owner_id, command.request_id
        )
    )
    if info is not None:
        if (
            info.source_media_id,
            info.file.size_bytes,
            info.sha256,
            info.file.content_type,
            info.file.original_filename,
        ) != (
            source_media_id,
            size_bytes,
            sha256,
            command.content_type,
            command.original_filename,
        ):
            raise Types.ProductFileVersionConflictError(
                "Upload key is bound to different image data or metadata."
            )
        return info
    entity = FileVersionsPersistenceMapper.upload_command_to_file_entity(
        command,
        file_version_id=uuid4(),
        source_media_id=source_media_id,
        storage_kind=storage_kind,
        storage_id=storage_id,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    reserved = FileVersionsPersistenceMapper.file_entity_to_storage_info(
        await FileVersionsRepository.insert_file_version(session, entity)
    )
    assert reserved is not None, "File reservation disappeared."
    return reserved


async def _find_import_request(
    session: AsyncSession, command: Types.ImportProductFileVersionCommand
) -> Types.ProductFileVersionInfo | None:
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id
        ),
    )
    info = FileVersionsPersistenceMapper.file_entity_to_storage_info(
        await FileVersionsRepository.get_file_request(
            session, command.product_id, command.owner_id, command.request_id
        )
    )
    if info is None:
        return None
    if info.source_media_id != command.media_id:
        raise Types.ProductFileVersionConflictError(
            "Upload key is bound to a different source."
        )
    return info.file if info.file.state != State.PENDING else None


async def _lock_owned_file_version(
    session: AsyncSession, command: Types.ReadOwnedProductFileVersionCommand
) -> FileStorageInfo:
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id
        ),
    )
    info = await _get_file_version(
        session, command.product_id, command.file_version_id, lock=True
    )
    if info is None or info.owner_id != command.owner_id:
        raise LookupError("File version not found.")
    return info


async def _get_owned_ready_file_version(
    session: AsyncSession, command: Types.ReadOwnedProductFileVersionCommand
) -> FileStorageInfo:
    await QueryService.get_owned_product(
        session,
        Types.OwnedProductCommand(
            product_id=command.product_id, owner_id=command.owner_id
        ),
    )
    info = await _get_file_version(
        session, command.product_id, command.file_version_id, lock=False
    )
    if (
        info is None
        or info.owner_id != command.owner_id
        or info.file.state != State.READY
    ):
        raise LookupError("File version not found.")
    return info


async def _complete_file_upload(
    session: AsyncSession,
    info: FileStorageInfo,
    stored: AssetStorageTypes.StoredAssetInfo,
) -> Types.ProductFileVersionInfo:
    if (
        stored.storage_kind,
        stored.storage_id,
        stored.object_key,
        stored.content_type,
        stored.size_bytes,
    ) != (
        info.storage_kind,
        info.storage_id,
        info.object_key,
        info.file.content_type,
        info.file.size_bytes,
    ):
        raise RuntimeError("Storage returned an inconsistent file identity.")
    await FileVersionsRepository.set_file_state(
        session, info.file.file_version_id, State.READY
    )
    await FileVersionsRepository.set_file_retention(
        session,
        info.file.file_version_id,
        awaiting_attachment=True,
        unreferenced_since=datetime.now(UTC),
    )
    return replace(info.file, state=State.READY)


async def retain_product_file_version(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> Types.ProductFileVersionInfo:
    """Pin the ready file in the same transaction as the caller's reference."""
    async with use_case_transaction(session):
        info = await _get_file_version(
            session, command.product_id, command.file_version_id, lock=True
        )
        if info is None or info.file.state != State.READY:
            raise LookupError("File version not found.")
        if not await FileVersionsRepository.has_file_reference(session, command):
            await FileVersionsRepository.insert_file_reference(session, command)
            if info.unreferenced_since is not None or info.awaiting_attachment:
                await FileVersionsRepository.set_file_retention(
                    session,
                    command.file_version_id,
                    awaiting_attachment=False,
                    unreferenced_since=None,
                )
        return info.file


async def release_product_file_version(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> None:
    """Drop the exact reference. A repeated release leaves the GC clock alone."""
    async with use_case_transaction(session):
        info = await _get_file_version(
            session, command.product_id, command.file_version_id, lock=True
        )
        if info is None:
            raise LookupError("File version not found.")
        if not await FileVersionsRepository.has_file_reference(session, command):
            return
        await FileVersionsRepository.delete_file_reference(session, command)
        if not await FileVersionsRepository.has_file_references(
            session, command.file_version_id
        ):
            await FileVersionsRepository.set_file_retention(
                session,
                command.file_version_id,
                awaiting_attachment=False,
                unreferenced_since=datetime.now(UTC),
            )


async def _get_referenced_file_version(
    session: AsyncSession, command: Types.ProductFileReferenceCommand
) -> FileStorageInfo:
    info = await _get_file_version(
        session, command.product_id, command.file_version_id, lock=False
    )
    if (
        info is None
        or info.file.state != State.READY
        or not await FileVersionsRepository.has_file_reference(session, command)
    ):
        raise LookupError("File version not found.")
    return info


async def _prepare_file_cleanup(
    session: AsyncSession, command: Types.GetProductFileVersionCommand
) -> FileStorageInfo | Types.CleanupProductFileVersionInfo:
    info = await _get_file_version(
        session, command.product_id, command.file_version_id, lock=True
    )
    if info is None or info.file.state == State.DELETED:
        return Types.CleanupProductFileVersionInfo(False, "absent_or_deleted")
    if info.awaiting_attachment:
        return Types.CleanupProductFileVersionInfo(False, "awaiting_attachment")
    if await FileVersionsRepository.has_file_references(
        session, command.file_version_id
    ):
        return Types.CleanupProductFileVersionInfo(False, "referenced")
    if info.file.state != State.DELETING:
        if (
            info.unreferenced_since is None
            or datetime.now(UTC) - info.unreferenced_since < _RETENTION
        ):
            return Types.CleanupProductFileVersionInfo(False, "retention")
        await FileVersionsRepository.set_file_state(
            session, command.file_version_id, State.DELETING
        )
    return info


async def _lock_file_cleanup(
    session: AsyncSession, command: Types.GetProductFileVersionCommand
) -> FileStorageInfo | None:
    info = await _get_file_version(
        session, command.product_id, command.file_version_id, lock=True
    )
    if info is None or info.file.state == State.DELETED:
        return None
    if info.file.state != State.DELETING:
        raise RuntimeError("File deletion was not reserved.")
    return info


async def _complete_file_cleanup(
    session: AsyncSession, command: Types.GetProductFileVersionCommand
) -> None:
    await FileVersionsRepository.set_file_state(
        session, command.file_version_id, State.DELETED
    )


async def _get_file_version(
    session: AsyncSession, product_id: UUID, file_version_id: UUID, *, lock: bool
) -> FileStorageInfo | None:
    return FileVersionsPersistenceMapper.file_entity_to_storage_info(
        await FileVersionsRepository.get_file_version(
            session,
            Types.GetProductFileVersionCommand(
                product_id=product_id, file_version_id=file_version_id
            ),
            lock=lock,
        )
    )
