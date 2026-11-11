from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.db.models.product_file_version import ProductFileVersion
from app.modules.content.product import types as Types


@dataclass(frozen=True, slots=True)
class FileStorageInfo:
    file: Types.ProductFileVersionInfo
    owner_id: UUID
    source_media_id: UUID | None
    storage_kind: str
    storage_id: str
    object_key: str
    sha256: str
    awaiting_attachment: bool
    unreferenced_since: datetime | None


def file_entity_to_storage_info(
    entity: ProductFileVersion | None,
) -> FileStorageInfo | None:
    if entity is None:
        return None
    return FileStorageInfo(
        file=Types.ProductFileVersionInfo(
            product_id=entity.product_id,
            file_version_id=entity.id,
            content_type=entity.content_type,
            size_bytes=entity.size_bytes,
            original_filename=entity.original_filename,
            state=Types.ProductFileVersionState(entity.state),
        ),
        owner_id=entity.owner_id,
        source_media_id=entity.source_media_id,
        storage_kind=entity.storage_kind,
        storage_id=entity.storage_id,
        object_key=entity.object_key,
        sha256=entity.sha256,
        awaiting_attachment=entity.awaiting_attachment,
        unreferenced_since=entity.unreferenced_since,
    )


def upload_command_to_file_entity(
    command: Types.UploadProductFileVersionCommand,
    *,
    file_version_id: UUID,
    source_media_id: UUID | None,
    storage_kind: str,
    storage_id: str,
    size_bytes: int,
    sha256: str,
) -> ProductFileVersion:
    return ProductFileVersion(
        id=file_version_id,
        product_id=command.product_id,
        owner_id=command.owner_id,
        request_id=command.request_id,
        source_media_id=source_media_id,
        storage_kind=storage_kind,
        storage_id=storage_id,
        object_key=f"product-media/{command.product_id.hex}/{file_version_id.hex}",
        content_type=command.content_type,
        size_bytes=size_bytes,
        original_filename=command.original_filename,
        sha256=sha256,
        state=Types.ProductFileVersionState.PENDING,
    )
