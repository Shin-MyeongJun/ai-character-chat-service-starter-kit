# 검수 상태 변경 전에 HTTP moderator dependency를 검사한다. 현재 기본 dependency는 503이다.
# owner_id는 요청 행위자이며 실제 대상 조회는 content의 상태 변경 Command에 위임한다.
"""HTTP adapter for lorebook management operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.http.lorebook_dependencies import (
    get_current_owner_id,
    get_lorebook_session,
    require_lorebook_moderator,
)
from app.modules.content.lorebook.service import command as LorebookCommandService
from app.modules.governance.moderation.mapper.lorebook import (
    LorebookSchemaMapper as SchemaMapper,
)
from app.modules.governance.moderation.schemas import lorebook as schemas

router = APIRouter(prefix="/lorebooks", tags=["lorebooks"])
SessionDependency = Annotated[AsyncSession, Depends(get_lorebook_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner_id)]
LorebookListRequest = Annotated[schemas.ListLorebooksRequestDto, Query()]
EntryListRequest = Annotated[schemas.ListLorebookEntriesRequestDto, Query()]


@contextmanager
def _service_errors() -> Iterator[None]:
    try:
        yield
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Lorebook resource not found."
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid lorebook input.",
        ) from exc


@router.patch(
    "/status",
    response_model=schemas.ChangeLorebookStatusResponseDto,
    dependencies=[Depends(require_lorebook_moderator)],
)
async def change_lorebook_status(
    request: schemas.ChangeLorebookStatusRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.ChangeLorebookStatusResponseDto:
    value = SchemaMapper.change_lorebook_status_request_to_command(request, owner_id)
    with _service_errors():
        result = await LorebookCommandService.change_lorebook_status(session, value)
    return SchemaMapper.lorebook_info_to_status_response(result)
