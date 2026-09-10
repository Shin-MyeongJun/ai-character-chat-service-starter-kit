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
    require_lorebook_admin,
)
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.governance.admin.mapper.lorebook import (
    LorebookSchemaMapper as SchemaMapper,
)
from app.modules.governance.admin.schemas import lorebook as schemas

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


@router.get(
    "",
    response_model=schemas.ListLorebooksResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def list_lorebooks(
    request: LorebookListRequest, session: SessionDependency
) -> schemas.ListLorebooksResponseDto:
    cursor = SchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await LorebookQueryService.list_lorebooks(
            session,
            LorebookTypes.ListLorebooksCommand(cursor=cursor, limit=request.limit),
        )
    return SchemaMapper.lorebook_page_to_response(result)


@router.get(
    "/{lorebook_id}",
    response_model=schemas.GetLorebookByIdResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def get_lorebook(
    lorebook_id: UUID, session: SessionDependency
) -> schemas.GetLorebookByIdResponseDto:
    with _service_errors():
        result = await LorebookQueryService.get_lorebook_by_id(
            session, LorebookTypes.GetLorebookByIdCommand(lorebook_id=lorebook_id)
        )
        if result is None:
            raise LookupError("Lorebook not found.")
    return SchemaMapper.lorebook_info_to_get_response(result)


@router.get(
    "/{lorebook_id}/entries",
    response_model=schemas.ListLorebookEntriesResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def list_entries(
    lorebook_id: UUID, request: EntryListRequest, session: SessionDependency
) -> schemas.ListLorebookEntriesResponseDto:
    cursor = SchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        parent = await LorebookQueryService.get_lorebook_by_id(
            session, LorebookTypes.GetLorebookByIdCommand(lorebook_id=lorebook_id)
        )
        if parent is None:
            raise LookupError("Lorebook not found.")
        result = await LorebookQueryService.list_lorebook_entries(
            session,
            LorebookTypes.ListLorebookEntriesCommand(
                lorebook_id=lorebook_id, cursor=cursor, limit=request.limit
            ),
        )
    return SchemaMapper.entry_page_to_response(result)


@router.get(
    "/{lorebook_id}/entries/{entry_id}",
    response_model=schemas.GetLorebookEntryResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def get_entry(
    lorebook_id: UUID, entry_id: UUID, session: SessionDependency
) -> schemas.GetLorebookEntryResponseDto:
    with _service_errors():
        result = await LorebookQueryService.get_lorebook_entry(
            session,
            LorebookTypes.GetLorebookEntryCommand(
                lorebook_id=lorebook_id, entry_id=entry_id
            ),
        )
        if result is None:
            raise LookupError("Lorebook entry not found.")
    return SchemaMapper.entry_info_to_get_response(result)
