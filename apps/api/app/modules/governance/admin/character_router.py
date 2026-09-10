"""HTTP adapter for character commands and router-oriented queries."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.character_dependencies import (
    get_character_session,
    get_current_owner_id,
    require_character_admin,
)
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.governance.admin.mapper.character import (
    CharacterSchemaMapper as SchemaMapper,
)
from app.modules.governance.admin.schemas import character as schemas

router = APIRouter(prefix="/characters", tags=["characters"])
SessionDependency = Annotated[AsyncSession, Depends(get_character_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner_id)]
ListRequest = Annotated[schemas.ListCharactersRequestDto, Query()]


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


@router.get(
    "",
    response_model=schemas.ListCharactersResponseDto,
    dependencies=[Depends(require_character_admin)],
)
async def list_characters(
    request: ListRequest, session: SessionDependency
) -> schemas.ListCharactersResponseDto:
    cursor = SchemaMapper.list_characters_request_to_cursor(request)
    with _service_errors():
        result = await CharacterQueryService.list_characters(
            session,
            CharacterTypes.ListCharactersCommand(cursor=cursor, limit=request.limit),
        )
    return SchemaMapper.character_page_to_list_response(result)


@router.get(
    "/{character_id}",
    response_model=schemas.GetCharacterByIdResponseDto,
    dependencies=[Depends(require_character_admin)],
)
async def get_character(
    character_id: UUID, session: SessionDependency
) -> schemas.GetCharacterByIdResponseDto:
    with _service_errors():
        result = await CharacterQueryService.get_character_by_id(
            session, CharacterTypes.GetCharacterByIdCommand(character_id=character_id)
        )
        if result is None:
            raise LookupError("Character not found.")
    return SchemaMapper.character_info_to_get_response(result)
