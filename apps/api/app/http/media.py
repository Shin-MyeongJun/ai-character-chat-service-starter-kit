# 바이너리 업로드를 최대 32 MiB까지 임시 스트림에 모아 미디어 서비스에 전달한다.
# 읽기 권한 확인 후 64 KiB씩 전송하며 전송 완료·실패 모두 reader를 닫는다.
# 전송 시작 뒤 발생한 읽기 오류는 media_errors의 HTTP 변환 범위 밖이다.
"""Additive binary HTTP transport; existing JSON media DTOs remain unchanged."""

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from tempfile import SpooledTemporaryFile
from typing import Annotated, BinaryIO, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.http.character_dependencies import get_current_owner_id
from app.http.dependencies import Owner
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.media import (
    MAX_MEDIA_BYTES,
    MEDIA_CONTENT_TYPES,
)
from app.modules.content.character.service.workflow.media import CharacterMediaWorkflow
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.views.media import ProductMediaService

router = APIRouter(tags=["media"])
CharacterOwner = Annotated[UUID, Depends(get_current_owner_id)]


class UploadCharacterMediaResponseDto(BaseModel):
    media_id: UUID
    content_url: str
    content_type: str
    size_bytes: int
    original_filename: str
    purpose: str


def get_character_media_service(request: Request) -> CharacterMediaWorkflow:
    # main installs this workflow; retain injected runtime/test doubles and the
    # existing AttributeError when the state member is absent.
    return cast(CharacterMediaWorkflow, request.app.state.character_media_service)


def get_product_media_service(request: Request) -> ProductMediaService:
    # main constructs this service from the configured session/media dependencies.
    return cast(ProductMediaService, request.app.state.product_media_service)


@contextmanager
def media_errors() -> Iterator[None]:
    try:
        yield
    except (LookupError, AssetStorageTypes.AssetNotFoundError) as exc:
        raise HTTPException(404, "Media not found.") from exc
    except AssetStorageTypes.AssetStorageConfigurationError as exc:
        raise HTTPException(503, "Recorded media storage is unavailable.") from exc
    except AssetStorageTypes.AssetStorageError as exc:
        raise HTTPException(503, "Media storage operation failed.") from exc
    except ValueError as exc:
        raise HTTPException(
            422, "Invalid media input or conflicting upload request."
        ) from exc


class MediaStreamingResponse(StreamingResponse):
    def __init__(self, opened: AssetStorageTypes.AssetReadInfo) -> None:
        self.opened = opened

        async def chunks() -> AsyncIterator[bytes]:
            while chunk := await opened.read(64 * 1024):
                yield chunk

        super().__init__(
            chunks(),
            media_type=opened.metadata.content_type,
            headers={
                "Content-Length": str(opened.metadata.size_bytes),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": "inline",
            },
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.opened.aclose()


@router.post(
    "/characters/{character_id}/media/uploads",
    response_model=UploadCharacterMediaResponseDto,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                content_type: {"schema": {"type": "string", "format": "binary"}}
                for content_type in sorted(MEDIA_CONTENT_TYPES)
            },
        }
    },
)
async def upload_character_media(
    character_id: UUID,
    request: Request,
    owner: CharacterOwner,
    service: Annotated[CharacterMediaWorkflow, Depends(get_character_media_service)],
    idempotency_key: Annotated[UUID, Header()],
    content_type: Annotated[str, Header()],
    x_filename: Annotated[str, Header(min_length=1, max_length=255)],
    x_media_purpose: Annotated[str, Header(min_length=1, max_length=200)],
) -> UploadCharacterMediaResponseDto:
    with media_errors(), SpooledTemporaryFile(max_size=1024 * 1024) as content:
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_MEDIA_BYTES:
                raise HTTPException(413, "Media exceeds 32 MiB.")
            content.write(chunk)
        info = await service.upload_character_media(
            CharacterTypes.UploadCharacterMediaCommand(
                character_id=character_id,
                owner_id=owner,
                request_id=idempotency_key,
                # The default w+b spool implements the seek/read binary interface
                # used by fingerprinting/storage; its stub is not nominal BinaryIO.
                content=cast(BinaryIO, content),
                content_type=content_type,
                original_filename=x_filename,
                purpose=x_media_purpose,
            )
        )
    return UploadCharacterMediaResponseDto(
        media_id=info.id,
        content_url=info.content_url,
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        original_filename=info.original_filename,
        purpose=info.purpose,
    )


@router.get("/characters/media/{media_id}/content")
async def read_character_media(
    media_id: UUID,
    owner: CharacterOwner,
    service: Annotated[CharacterMediaWorkflow, Depends(get_character_media_service)],
) -> MediaStreamingResponse:
    with media_errors():
        opened = await service.read_character_media(
            CharacterTypes.ReadCharacterMediaCommand(media_id=media_id, owner_id=owner)
        )
    return MediaStreamingResponse(opened)


@router.get("/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content")
async def read_product_media(
    product_id: UUID,
    snapshot_id: UUID,
    media_id: UUID,
    owner: Owner,
    service: Annotated[ProductMediaService, Depends(get_product_media_service)],
) -> MediaStreamingResponse:
    with media_errors():
        opened = await service.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                product_id=product_id,
                snapshot_id=snapshot_id,
                media_id=media_id,
                user_id=owner,
            )
        )
    return MediaStreamingResponse(opened)
