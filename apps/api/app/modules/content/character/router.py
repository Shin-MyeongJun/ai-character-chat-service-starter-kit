"""HTTP adapter for character commands and router-oriented queries."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.character import schemas as Schemas
from app.modules.content.character import types as Types
from app.modules.content.character.dependencies import (
    get_character_session,
    get_current_owner_id,
)
from app.modules.content.character.mapper.schema import (
    CharacterSchemaMapper as SchemaMapper,
)
from app.modules.content.character.service import command as CommandService
from app.modules.content.character.service import query as QueryService

router = APIRouter(prefix="/characters", tags=["characters"])
SessionDependency = Annotated[AsyncSession, Depends(get_character_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner_id)]
ListRequest = Annotated[Schemas.ListCharactersRequestDto, Query()]


@contextmanager
def _service_errors() -> Iterator[None]:
    try:
        yield
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character resource not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid character input.",
        ) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Character operation is not implemented yet.",
        ) from exc


@router.get("/me", response_model=Schemas.ListCharactersResponseDto)
async def list_my_characters(
    request: ListRequest, owner_id: OwnerDependency, session: SessionDependency
) -> Schemas.ListCharactersResponseDto:
    cursor = SchemaMapper.list_characters_request_to_cursor(request)
    with _service_errors():
        result = await QueryService.list_characters_by_owner_id(
            session,
            Types.ListCharactersByOwnerIdCommand(
                owner_id=owner_id, cursor=cursor, limit=request.limit
            ),
        )
    return SchemaMapper.character_page_to_list_response(result)


@router.get("/me/{character_id}", response_model=Schemas.GetCharacterByIdResponseDto)
async def get_my_character(
    character_id: UUID, owner_id: OwnerDependency, session: SessionDependency
) -> Schemas.GetCharacterByIdResponseDto:
    with _service_errors():
        result = await QueryService.get_character_by_id_and_owner_id(
            session,
            Types.GetCharacterByIdAndOwnerIdCommand(
                character_id=character_id, owner_id=owner_id
            ),
        )
        if result is None:
            raise LookupError("Character not found.")
    return SchemaMapper.character_info_to_get_response(result)


@router.post(
    "",
    response_model=Schemas.CreateCharacterResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_character(
    request: Schemas.CreateCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.CreateCharacterResponseDto:
    value = SchemaMapper.create_character_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.create_character(session, value)
    return SchemaMapper.character_info_to_create_response(result)


@router.put("", response_model=Schemas.UpdateCharacterResponseDto)
async def update_character(
    request: Schemas.UpdateCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.UpdateCharacterResponseDto:
    value = SchemaMapper.update_character_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.update_character(session, value)
    return SchemaMapper.character_info_to_update_response(result)


@router.delete("", response_model=Schemas.DeleteCharacterResponseDto)
async def delete_character(
    request: Schemas.DeleteCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.DeleteCharacterResponseDto:
    value = SchemaMapper.delete_character_request_to_command(request, owner_id)
    with _service_errors():
        await CommandService.delete_character(session, value)
    return SchemaMapper.delete_character_result_to_response(None)


@router.post(
    "/images",
    response_model=Schemas.AddCharacterImageResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def add_character_image(
    request: Schemas.AddCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.AddCharacterImageResponseDto:
    value = SchemaMapper.add_character_image_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.add_character_image(session, value)
    return SchemaMapper.character_image_info_to_add_response(result)


@router.patch(
    "/images/default", response_model=Schemas.SetDefaultCharacterImageResponseDto
)
async def set_default_character_image(
    request: Schemas.SetDefaultCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.SetDefaultCharacterImageResponseDto:
    value = SchemaMapper.set_default_character_image_request_to_command(
        request, owner_id
    )
    with _service_errors():
        result = await CommandService.set_default_character_image(session, value)
    return SchemaMapper.character_image_info_to_default_response(result)


@router.delete("/images", response_model=Schemas.DeleteCharacterImageResponseDto)
async def delete_character_image(
    request: Schemas.DeleteCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.DeleteCharacterImageResponseDto:
    value = SchemaMapper.delete_character_image_request_to_command(request, owner_id)
    with _service_errors():
        await CommandService.delete_character_image(session, value)
    return SchemaMapper.delete_character_image_result_to_response(None)


@router.post(
    "/assets",
    response_model=Schemas.AddCharacterAssetResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def add_character_asset(
    request: Schemas.AddCharacterAssetRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.AddCharacterAssetResponseDto:
    value = SchemaMapper.add_character_asset_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.add_character_asset(session, value)
    return SchemaMapper.character_asset_info_to_add_response(result)


@router.delete("/assets", response_model=Schemas.DeleteCharacterAssetResponseDto)
async def delete_character_asset(
    request: Schemas.DeleteCharacterAssetRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.DeleteCharacterAssetResponseDto:
    value = SchemaMapper.delete_character_asset_request_to_command(request, owner_id)
    with _service_errors():
        await CommandService.delete_character_asset(session, value)
    return SchemaMapper.delete_character_asset_result_to_response(None)
