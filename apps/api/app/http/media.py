"""Additive binary HTTP transport; existing JSON media DTOs remain unchanged."""

from contextlib import contextmanager
from tempfile import SpooledTemporaryFile
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.http.character_dependencies import get_current_owner_id
from app.http.dependencies import Owner
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.media import (
    MAX_MEDIA_BYTES,
    MEDIA_CONTENT_TYPES,
    CharacterMediaService,
)
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


def get_character_media_service(request: Request) -> CharacterMediaService:
    return request.app.state.character_media_service


def get_product_media_service(request: Request) -> ProductMediaService:
    return request.app.state.product_media_service


@contextmanager
def media_errors():
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
    def __init__(self, opened: AssetStorageTypes.AssetReadInfo):
        self.opened = opened

        async def chunks():
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

    async def __call__(self, scope, receive, send):
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
    service: Annotated[CharacterMediaService, Depends(get_character_media_service)],
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
                character_id,
                owner,
                idempotency_key,
                content,
                content_type,
                x_filename,
                x_media_purpose,
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
    service: Annotated[CharacterMediaService, Depends(get_character_media_service)],
):
    with media_errors():
        opened = await service.read_character_media(
            CharacterTypes.ReadCharacterMediaCommand(media_id, owner)
        )
    return MediaStreamingResponse(opened)


@router.get("/products/{product_id}/versions/{snapshot_id}/media/{media_id}/content")
async def read_product_media(
    product_id: UUID,
    snapshot_id: UUID,
    media_id: UUID,
    owner: Owner,
    service: Annotated[ProductMediaService, Depends(get_product_media_service)],
):
    with media_errors():
        opened = await service.read_product_media(
            ProductTypes.ReadProductMediaCommand(
                product_id, snapshot_id, media_id, owner
            )
        )
    return MediaStreamingResponse(opened)
