# 업로드 예약을 먼저 커밋한 뒤 객체 저장·ready 확정을 수행한다. DB 실패 시 pending으로 같은 요청을 재개한다.
# 객체 저장과 DB는 원자적이지 않으므로 모호한 커밋 실패에 즉시 파일을 보상 삭제하지 않는다.
"""Durable upload intents, immutable objects, authorized reads and explicit GC."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, overload
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.db.types import SessionFactory
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.asset_storage.service import AssetStorageService
from app.modules.content.character import repository as MediaRepository
from app.modules.content.character import types as Types
from app.modules.content.character.mapper import media as MediaPersistenceMapper
from app.modules.content.character.mapper import persistence as PersistenceMapper
from app.modules.content.character.service.command import _get_owned_character

MAX_MEDIA_BYTES = 32 * 1024 * 1024
MEDIA_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "video/mp4",
        "video/webm",
    }
)


def _fingerprint_upload(command: Types.UploadCharacterMediaCommand) -> tuple[int, str]:
    if command.content_type not in MEDIA_CONTENT_TYPES:
        raise ValueError("Unsupported media content type.")
    filename = command.original_filename
    if (
        not filename
        or len(filename) > 255
        or any(c in filename for c in "/\\")
        or any(ord(c) < 32 for c in filename)
    ):
        raise ValueError("Use an original filename without a path.")
    if not command.purpose.strip() or len(command.purpose) > 200:
        raise ValueError("Invalid media purpose.")
    digest = hashlib.sha256()
    size = 0
    command.content.seek(0)
    while chunk := command.content.read(64 * 1024):
        size += len(chunk)
        if size > MAX_MEDIA_BYTES:
            raise ValueError("Media exceeds 32 MiB.")
        digest.update(chunk)
    command.content.seek(0)
    if size == 0:
        raise ValueError("Empty media.")
    return size, digest.hexdigest()


class CharacterMediaService:
    def __init__(
        self,
        sessions: SessionFactory,
        storage: AssetStorageService,
        *,
        storage_kind: str,
        storage_id: str,
        read_storages: dict[tuple[str, str], AssetStorageService] | None = None,
    ) -> None:
        self.sessions = sessions
        self.storage = storage
        self.storage_kind = storage_kind
        self.storage_id = storage_id
        self.storages = dict(read_storages or {})
        self.storages[(storage_kind, storage_id)] = storage

    def _storage_for_media(self, info: Types.CharacterMediaInfo) -> AssetStorageService:
        try:
            return self.storages[(info.storage_kind, info.storage_id)]
        except KeyError as exc:
            raise AssetStorageTypes.AssetStorageConfigurationError(
                "The recorded media storage is not configured."
            ) from exc

    async def reserve_upload(
        self, session: AsyncSession, command: Types.UploadCharacterMediaCommand
    ) -> Types.CharacterMediaInfo:
        size, digest = _fingerprint_upload(command)
        await _get_owned_character(session, command.character_id, command.owner_id)
        row = await MediaRepository.get_media_request(session, command)
        info = MediaPersistenceMapper.media_entity_to_info(row)
        new_upload = info is None
        if info is None:
            media_id = uuid4()
            info = Types.CharacterMediaInfo(
                media_id,
                command.character_id,
                command.owner_id,
                command.request_id,
                self.storage_kind,
                self.storage_id,
                f"character-media/{media_id.hex}",
                command.content_type,
                size,
                command.original_filename,
                command.purpose,
                digest,
                "pending",
                None,
                datetime.now(UTC),
            )
            await MediaRepository.create_media(session, info)
        if (
            info.size_bytes,
            info.sha256,
            info.content_type,
            info.original_filename,
            info.purpose,
        ) != (
            size,
            digest,
            command.content_type,
            command.original_filename,
            command.purpose,
        ):
            raise ValueError("Idempotency key reused with different media.")
        if not new_upload and info.state == "pending":
            # Commit a fresh attempt timestamp before I/O. A crashed retry
            # must receive the same GC grace period as the first attempt.
            await MediaRepository.set_media_state(session, info.id, "pending")
        return info

    async def lock_upload(
        self, session: AsyncSession, command: Types.LockMediaUploadCommand
    ) -> Types.CharacterMediaInfo:
        await _get_owned_character(session, command.character_id, command.owner_id)
        row = await MediaRepository.get_media(session, command.media_id, lock=True)
        info = MediaPersistenceMapper.media_entity_to_info(row)
        if (
            info is None
            or info.character_id != command.character_id
            or info.owner_id != command.owner_id
        ):
            raise LookupError("Media not found.")
        if info.state == "ready":
            return info
        if info.state != "pending":
            raise ValueError("This upload was retired; use a new request ID.")
        return info

    async def complete_upload(
        self, session: AsyncSession, command: Types.CompleteMediaUploadCommand
    ) -> Types.CharacterMediaInfo:
        info = await self.lock_upload(
            session,
            Types.LockMediaUploadCommand(
                command.media.id, command.media.character_id, command.media.owner_id
            ),
        )
        stored = command.stored
        if (
            str(stored.storage_kind),
            stored.storage_id,
            stored.object_key,
            stored.size_bytes,
            stored.content_type,
        ) != (
            info.storage_kind,
            info.storage_id,
            info.object_key,
            info.size_bytes,
            info.content_type,
        ):
            raise RuntimeError("Storage returned an inconsistent media identity.")
        await MediaRepository.set_media_state(session, info.id, "ready")
        row = await MediaRepository.get_media(session, info.id)
        result = MediaPersistenceMapper.media_entity_to_info(row)
        # A commit failure propagates. The committed reservation remains;
        # no unsafe compensation deletion on an ambiguous commit outcome.
        # The reservation remains locked; state update does not delete its row.
        assert result is not None, "Locked media reservation disappeared."
        return result

    # 현재 캐릭터 소유권과 ready 상태·설정된 저장소를 확인한 뒤 열린 reader를 반환한다.
    async def read_character_media(
        self, command: Types.ReadCharacterMediaCommand
    ) -> AssetStorageTypes.AssetReadInfo:
        async with self.sessions() as session, use_case_transaction(session):
            row = await MediaRepository.get_media(session, command.media_id)
            info = MediaPersistenceMapper.media_entity_to_info(row)
            if (
                info is None
                or info.owner_id != command.owner_id
                or info.state != "ready"
            ):
                raise LookupError("Media not found.")
            await _get_owned_character(session, info.character_id, command.owner_id)
        return await self._storage_for_media(info).read_asset(
            AssetStorageTypes.ReadAssetCommand(info.object_key)
        )

    # 호출자가 접근을 확인한 캐릭터 스냅샷에 실제 참조된 미디어만 읽는다. 원본 소유자 조회로 대체하지 않는다.
    async def read_snapshot_media(
        self, command: Types.ReadSnapshotMediaCommand
    ) -> AssetStorageTypes.AssetReadInfo:
        """Trusted product service supplies only its authorized snapshot IDs."""
        async with self.sessions() as session, use_case_transaction(session):
            if not await MediaRepository.has_media_references(
                session, command.media_id, command.snapshot_ids
            ):
                raise LookupError("Media is not part of this version.")
            row = await MediaRepository.get_media(session, command.media_id)
            info = MediaPersistenceMapper.media_entity_to_info(row)
            if info is None or info.state != "ready":
                raise LookupError("Media not found.")
        return await self._storage_for_media(info).read_asset(
            AssetStorageTypes.ReadAssetCommand(info.object_key)
        )

    async def prepare_cleanup(
        self, session: AsyncSession, command: Types.CleanupCharacterMediaCommand
    ) -> Types.CharacterMediaInfo | Types.CleanupCharacterMediaInfo:
        if command.older_than.tzinfo is None or command.older_than > datetime.now(
            UTC
        ) - timedelta(hours=24):
            raise ValueError("Cleanup requires a cutoff at least 24 hours old.")
        row = await MediaRepository.get_media(session, command.media_id, lock=True)
        info = MediaPersistenceMapper.media_entity_to_info(row)
        if info is None or info.state == "deleted":
            return Types.CleanupCharacterMediaInfo(False, "absent_or_deleted")
        if info.state != "deleting" and info.updated_at >= command.older_than:
            return Types.CleanupCharacterMediaInfo(False, "retention")
        if await MediaRepository.has_media_references(session, info.id):
            return Types.CleanupCharacterMediaInfo(False, "referenced")
        # Reject future attachment/replay before deletion, even if a
        # worker dies after S3 succeeds but before final DB commit.
        await MediaRepository.set_media_state(session, info.id, "deleting")
        return info

    async def lock_cleanup(
        self, session: AsyncSession, command: Types.CleanupCharacterMediaCommand
    ) -> Types.CharacterMediaInfo | None:
        info = MediaPersistenceMapper.media_entity_to_info(
            await MediaRepository.get_media(session, command.media_id, lock=True)
        )
        if info is None or info.state == "deleted":
            return None
        if info.state != "deleting":
            raise ValueError("Media deletion was not reserved.")
        return info

    async def complete_cleanup(
        self, session: AsyncSession, command: Types.CleanupCharacterMediaCommand
    ) -> None:
        info = await self.lock_cleanup(session, command)
        if info is not None:
            await MediaRepository.set_media_state(session, info.id, "deleted")


@overload
async def _attach_character_media(
    session: AsyncSession,
    command: Types.CreateCharacterImageCommand,
    kind: Literal["image"],
) -> Types.CharacterImageInfo: ...


@overload
async def _attach_character_media(
    session: AsyncSession,
    command: Types.CreateCharacterAssetCommand,
    kind: Literal["asset"],
) -> Types.CharacterAssetInfo: ...


async def _attach_character_media(
    session: AsyncSession,
    command: Types.CreateCharacterImageCommand | Types.CreateCharacterAssetCommand,
    kind: Literal["image", "asset"],
) -> Types.CharacterImageInfo | Types.CharacterAssetInfo:
    await _get_owned_character(session, command.character_id, command.owner_id)
    # Public image/asset commands supply the matching literal kind; overloads encode it.
    if kind == "image":
        assert isinstance(command, Types.CreateCharacterImageCommand)
        url = command.image_url
    else:
        assert isinstance(command, Types.CreateCharacterAssetCommand)
        url = command.file_url
    media_id: UUID | None = None
    if not url.startswith("/characters/media/"):
        # Legacy references keep their URL meaning; never fetch arbitrary URLs
        # or read caller-supplied local paths in an online request.
        if (
            not url.strip()
            or "\\" in url
            or (len(url) > 1 and url[1] == ":")
            or url.startswith("/")
        ):
            raise ValueError("Invalid legacy media URL.")
    else:
        try:
            media_id = UUID(url.split("/")[3])
        except (ValueError, IndexError) as exc:
            raise ValueError("Invalid managed media URL.") from exc
        media_row = await MediaRepository.get_media(session, media_id, lock=True)
        info = MediaPersistenceMapper.media_entity_to_info(media_row)
        if (
            info is None
            or info.owner_id != command.owner_id
            or info.character_id != command.character_id
        ):
            raise LookupError("Media not found.")
        if info.state != "ready" or url != info.content_url:
            raise ValueError("Media is not ready.")
        if kind == "image":
            assert isinstance(command, Types.CreateCharacterImageCommand)
            media_type = "image"
            binding_values = [kind, command.emotion_tag, command.is_default]
        else:
            assert isinstance(command, Types.CreateCharacterAssetCommand)
            media_type = command.asset_type
            binding_values = [kind, command.asset_type, command.purpose]
        if not info.content_type.startswith(media_type + "/"):
            raise ValueError("Media type does not match attachment.")
        binding = json.dumps(binding_values)
        if info.binding is not None and info.binding != binding:
            raise ValueError(
                "Media already attached with different metadata; upload a new object."
            )
        existing: Types.CharacterImageInfo | Types.CharacterAssetInfo | None
        if kind == "image":
            existing = PersistenceMapper.character_image_entity_to_info(
                await MediaRepository.get_media_attachment(session, media_id, "image")
            )
        else:
            existing = PersistenceMapper.character_asset_entity_to_info(
                await MediaRepository.get_media_attachment(session, media_id, "asset")
            )
        if existing is not None:
            return existing
        if info.binding is not None:
            raise ValueError("Attachment was deleted; upload a new object.")
        await MediaRepository.bind_media(session, media_id, binding)
    if kind == "image":
        assert isinstance(command, Types.CreateCharacterImageCommand)
        return PersistenceMapper.character_image_entity_to_info(
            await MediaRepository.create_media_attachment(
                session, command, media_id, "image"
            )
        )
    assert isinstance(command, Types.CreateCharacterAssetCommand)
    return PersistenceMapper.character_asset_entity_to_info(
        await MediaRepository.create_media_attachment(
            session, command, media_id, "asset"
        )
    )
