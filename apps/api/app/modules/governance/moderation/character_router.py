# 검수 상태 변경 전에 HTTP moderator dependency를 검사한다. 현재 기본 dependency는 503이다.
# owner_id는 요청 행위자이며 실제 대상 조회는 content의 상태 변경 Command에 위임한다.
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
    require_character_moderator,
)
from app.modules.content.character.service import command as CharacterCommandService
from app.modules.governance.moderation.mapper.character import (
    CharacterSchemaMapper as SchemaMapper,
)
from app.modules.governance.moderation.schemas import character as schemas

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
    value = SchemaMapper.change_character_status_request_to_command(request, owner_id)
    with _service_errors():
        result = await CharacterCommandService.change_character_status(session, value)
    return SchemaMapper.character_info_to_status_change_response(result)
