"""HTTP adapter for character commands and router-oriented queries."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.character import schemas
from app.modules.content.character.dependencies import (
    get_character_session,
    get_current_owner_id,
    require_character_admin,
    require_character_moderator,
)
from app.modules.content.character.mapper.schema import CharacterSchemaMapper
from app.modules.content.character.service import command, query

router = APIRouter(prefix="/characters", tags=["characters"])

SessionDependency = Annotated[AsyncSession, Depends(get_character_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner_id)]
ListRequest = Annotated[schemas.ListCharactersRequestDto, Query()]


@contextmanager
def _service_errors() -> Iterator[None]:
    # TODO(error-codes): Replace built-in exceptions and generic HTTP details with
    # the service's typed errors/codes and the common API error response mapper.
    # Keep this bridge local until that contract exists. Do not classify arbitrary
    # DB/runtime failures as user errors or expose their exception text to clients.
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
        # Image/asset creation is currently waiting for storage implementation.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Character operation is not implemented yet.",
        ) from exc


# Router-oriented reads only. Full results include private data/persona_prompt;
# unrestricted reads require administration access, and /me uses a trusted ID.
# Register static /me before /{character_id} to keep it out of UUID validation.


@router.get(
    "",
    response_model=schemas.ListCharactersResponseDto,
    dependencies=[Depends(require_character_admin)],
)
async def list_characters(
    request: ListRequest,
    session: SessionDependency,
) -> schemas.ListCharactersResponseDto:
    cursor = CharacterSchemaMapper.list_characters_request_to_cursor(request)
    with _service_errors():
        result = await query.list_characters(session, cursor=cursor, limit=request.limit)
    return CharacterSchemaMapper.character_page_to_list_response(result)


@router.get("/me", response_model=schemas.ListCharactersResponseDto)
async def list_my_characters(
    request: ListRequest,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.ListCharactersResponseDto:
    cursor = CharacterSchemaMapper.list_characters_request_to_cursor(request)
    with _service_errors():
        result = await query.list_characters_by_owner_id(
            session, owner_id=owner_id, cursor=cursor, limit=request.limit
        )
    return CharacterSchemaMapper.character_page_to_list_response(result)


@router.get("/me/{character_id}", response_model=schemas.GetCharacterByIdResponseDto)
async def get_my_character(
    character_id: UUID,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.GetCharacterByIdResponseDto:
    with _service_errors():
        result = await query.get_character_by_id_and_owner_id(
            session, character_id=character_id, owner_id=owner_id
        )
        # TODO(error-codes): Replace the query's None contract with the shared
        # not-found handling when service query errors are standardized.
        if result is None:
            raise LookupError("Character not found.")
    return CharacterSchemaMapper.character_info_to_get_response(result)


@router.get(
    "/{character_id}",
    response_model=schemas.GetCharacterByIdResponseDto,
    dependencies=[Depends(require_character_admin)],
)
async def get_character(
    character_id: UUID,
    session: SessionDependency,
) -> schemas.GetCharacterByIdResponseDto:
    with _service_errors():
        result = await query.get_character_by_id(session, character_id=character_id)
        # TODO(error-codes): Match the future service query not-found contract.
        if result is None:
            raise LookupError("Character not found.")
    return CharacterSchemaMapper.character_info_to_get_response(result)


# TODO: Expose search/filter endpoints when the router-oriented query service is
# implemented. Prompt, promotion, and media read helpers remain internal use cases.


# Commands. Existing request DTOs carry resource IDs in JSON bodies, including
# DELETE requests. The authenticated owner ID is added only by the schema mapper.
# Service commands own commit/rollback; the router does not begin transactions.


@router.post(
    "", response_model=schemas.CreateCharacterResponseDto, status_code=status.HTTP_201_CREATED
)
async def create_character(
    request: schemas.CreateCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.CreateCharacterResponseDto:
    value = CharacterSchemaMapper.create_character_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.create_character(session, value)
    return CharacterSchemaMapper.character_info_to_create_response(result)


@router.put("", response_model=schemas.UpdateCharacterResponseDto)
async def update_character(
    request: schemas.UpdateCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.UpdateCharacterResponseDto:
    value = CharacterSchemaMapper.update_character_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.update_character(session, value)
    return CharacterSchemaMapper.character_info_to_update_response(result)


@router.patch(
    "/status",
    response_model=schemas.ChangeCharacterStatusResponseDto,
    dependencies=[Depends(require_character_moderator)],
)
async def change_character_status(
    request: schemas.ChangeCharacterStatusRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.ChangeCharacterStatusResponseDto:
    # The current command also requires ownership. TODO: Add a dedicated service
    # use case before allowing moderators to change another owner's character.
    value = CharacterSchemaMapper.change_character_status_request_to_command(
        request, owner_id
    )
    with _service_errors():
        result = await command.change_character_status(session, value)
    return CharacterSchemaMapper.character_info_to_status_change_response(result)


@router.delete("", response_model=schemas.DeleteCharacterResponseDto)
async def delete_character(
    request: schemas.DeleteCharacterRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.DeleteCharacterResponseDto:
    value = CharacterSchemaMapper.delete_character_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.delete_character(session, value)
    return CharacterSchemaMapper.delete_character_result_to_response(result)


@router.post(
    "/images",
    response_model=schemas.AddCharacterImageResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def add_character_image(
    request: schemas.AddCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.AddCharacterImageResponseDto:
    value = CharacterSchemaMapper.add_character_image_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.add_character_image(session, value)
    return CharacterSchemaMapper.character_image_info_to_add_response(result)


@router.patch("/images/default", response_model=schemas.SetDefaultCharacterImageResponseDto)
async def set_default_character_image(
    request: schemas.SetDefaultCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.SetDefaultCharacterImageResponseDto:
    value = CharacterSchemaMapper.set_default_character_image_request_to_command(
        request, owner_id
    )
    with _service_errors():
        result = await command.set_default_character_image(session, value)
    return CharacterSchemaMapper.character_image_info_to_default_response(result)


@router.delete("/images", response_model=schemas.DeleteCharacterImageResponseDto)
async def delete_character_image(
    request: schemas.DeleteCharacterImageRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.DeleteCharacterImageResponseDto:
    value = CharacterSchemaMapper.delete_character_image_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.delete_character_image(session, value)
    return CharacterSchemaMapper.delete_character_image_result_to_response(result)


@router.post(
    "/assets",
    response_model=schemas.AddCharacterAssetResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def add_character_asset(
    request: schemas.AddCharacterAssetRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.AddCharacterAssetResponseDto:
    value = CharacterSchemaMapper.add_character_asset_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.add_character_asset(session, value)
    return CharacterSchemaMapper.character_asset_info_to_add_response(result)


@router.delete("/assets", response_model=schemas.DeleteCharacterAssetResponseDto)
async def delete_character_asset(
    request: schemas.DeleteCharacterAssetRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.DeleteCharacterAssetResponseDto:
    value = CharacterSchemaMapper.delete_character_asset_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.delete_character_asset(session, value)
    return CharacterSchemaMapper.delete_character_asset_result_to_response(result)
