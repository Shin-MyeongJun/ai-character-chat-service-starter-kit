# 소유 로어북과 그 항목 관리 HTTP 경계. 부모가 미소유이면 항목 조회 전 404로 처리한다.
"""HTTP adapter for lorebook management operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.lorebook import schemas as Schemas
from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.dependencies import (
    get_current_owner_id,
    get_lorebook_session,
)
from app.modules.content.lorebook.mapper.schema import (
    LorebookSchemaMapper as SchemaMapper,
)
from app.modules.content.lorebook.service import command as CommandService
from app.modules.content.lorebook.service import query as QueryService

router = APIRouter(prefix="/lorebooks", tags=["lorebooks"])
SessionDependency = Annotated[AsyncSession, Depends(get_lorebook_session)]
OwnerDependency = Annotated[UUID, Depends(get_current_owner_id)]
LorebookListRequest = Annotated[Schemas.ListLorebooksRequestDto, Query()]
EntryListRequest = Annotated[Schemas.ListLorebookEntriesRequestDto, Query()]


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


@router.get("/me", response_model=Schemas.ListLorebooksResponseDto)
async def list_my_lorebooks(
    request: LorebookListRequest, owner_id: OwnerDependency, session: SessionDependency
) -> Schemas.ListLorebooksResponseDto:
    cursor = SchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await QueryService.list_lorebooks_by_owner_id(
            session,
            Types.ListLorebooksByOwnerIdCommand(
                owner_id=owner_id, cursor=cursor, limit=request.limit
            ),
        )
    return SchemaMapper.lorebook_page_to_response(result)


@router.get("/me/{lorebook_id}", response_model=Schemas.GetLorebookByIdResponseDto)
async def get_my_lorebook(
    lorebook_id: UUID, owner_id: OwnerDependency, session: SessionDependency
) -> Schemas.GetLorebookByIdResponseDto:
    with _service_errors():
        result = await QueryService.get_lorebook_by_id_and_owner_id(
            session,
            Types.GetLorebookByIdAndOwnerIdCommand(
                lorebook_id=lorebook_id, owner_id=owner_id
            ),
        )
        if result is None:
            raise LookupError("Lorebook not found.")
    return SchemaMapper.lorebook_info_to_get_response(result)


@router.get(
    "/me/{lorebook_id}/entries", response_model=Schemas.ListLorebookEntriesResponseDto
)
async def list_my_lorebook_entries(
    lorebook_id: UUID,
    request: EntryListRequest,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.ListLorebookEntriesResponseDto:
    cursor = SchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await QueryService.list_lorebook_entries_by_owner_id(
            session,
            Types.ListLorebookEntriesByOwnerIdCommand(
                lorebook_id=lorebook_id,
                owner_id=owner_id,
                cursor=cursor,
                limit=request.limit,
            ),
        )
        if result is None:
            raise LookupError("Lorebook not found.")
    return SchemaMapper.entry_page_to_response(result)


@router.get(
    "/me/{lorebook_id}/entries/{entry_id}",
    response_model=Schemas.GetLorebookEntryResponseDto,
)
async def get_my_lorebook_entry(
    lorebook_id: UUID,
    entry_id: UUID,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.GetLorebookEntryResponseDto:
    with _service_errors():
        result = await QueryService.get_lorebook_entry_by_owner_id(
            session,
            Types.GetLorebookEntryByOwnerIdCommand(
                lorebook_id=lorebook_id, entry_id=entry_id, owner_id=owner_id
            ),
        )
        if result is None:
            raise LookupError("Lorebook entry not found.")
    return SchemaMapper.entry_info_to_get_response(result)


@router.post(
    "",
    response_model=Schemas.CreateLorebookResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_lorebook(
    request: Schemas.CreateLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.CreateLorebookResponseDto:
    value = SchemaMapper.create_lorebook_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.create_lorebook(session, value)
    return SchemaMapper.lorebook_info_to_create_response(result)


@router.put("", response_model=Schemas.UpdateLorebookResponseDto)
async def update_lorebook(
    request: Schemas.UpdateLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.UpdateLorebookResponseDto:
    value = SchemaMapper.update_lorebook_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.update_lorebook(session, value)
    return SchemaMapper.lorebook_info_to_update_response(result)


@router.delete("", response_model=Schemas.DeleteLorebookResponseDto)
async def delete_lorebook(
    request: Schemas.DeleteLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.DeleteLorebookResponseDto:
    value = SchemaMapper.delete_lorebook_request_to_command(request, owner_id)
    with _service_errors():
        await CommandService.delete_lorebook(session, value)
    return SchemaMapper.delete_lorebook_result_to_response(None)


@router.post(
    "/entries",
    response_model=Schemas.CreateLorebookEntryResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_lorebook_entry(
    request: Schemas.CreateLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.CreateLorebookEntryResponseDto:
    value = SchemaMapper.create_entry_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.create_lorebook_entry(session, value)
    return SchemaMapper.entry_info_to_create_response(result)


@router.put("/entries", response_model=Schemas.UpdateLorebookEntryResponseDto)
async def update_lorebook_entry(
    request: Schemas.UpdateLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.UpdateLorebookEntryResponseDto:
    value = SchemaMapper.update_entry_request_to_command(request, owner_id)
    with _service_errors():
        result = await CommandService.update_lorebook_entry(session, value)
    return SchemaMapper.entry_info_to_update_response(result)


@router.delete("/entries", response_model=Schemas.DeleteLorebookEntryResponseDto)
async def delete_lorebook_entry(
    request: Schemas.DeleteLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> Schemas.DeleteLorebookEntryResponseDto:
    value = SchemaMapper.delete_entry_request_to_command(request, owner_id)
    with _service_errors():
        await CommandService.delete_lorebook_entry(session, value)
    return SchemaMapper.delete_entry_result_to_response(None)
