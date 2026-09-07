"""HTTP adapter for lorebook management operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.lorebook import schemas
from app.modules.lorebook.dependencies import (
    get_current_owner_id,
    get_lorebook_session,
    require_lorebook_admin,
    require_lorebook_moderator,
)
from app.modules.lorebook.mapper.schema import LorebookSchemaMapper
from app.modules.lorebook.service import command, query

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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lorebook resource not found.",
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
    request: LorebookListRequest,
    session: SessionDependency,
) -> schemas.ListLorebooksResponseDto:
    cursor = LorebookSchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await query.list_lorebooks(
            session,
            cursor=cursor,
            limit=request.limit,
        )
    return LorebookSchemaMapper.lorebook_page_to_response(result)


@router.get("/me", response_model=schemas.ListLorebooksResponseDto)
async def list_my_lorebooks(
    request: LorebookListRequest,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.ListLorebooksResponseDto:
    cursor = LorebookSchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await query.list_lorebooks_by_owner_id(
            session,
            owner_id=owner_id,
            cursor=cursor,
            limit=request.limit,
        )
    return LorebookSchemaMapper.lorebook_page_to_response(result)


@router.get("/me/{lorebook_id}", response_model=schemas.GetLorebookByIdResponseDto)
async def get_my_lorebook(
    lorebook_id: UUID,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.GetLorebookByIdResponseDto:
    with _service_errors():
        result = await query.get_lorebook_by_id_and_owner_id(
            session,
            lorebook_id=lorebook_id,
            owner_id=owner_id,
        )
        if result is None:
            raise LookupError("Lorebook not found.")
    return LorebookSchemaMapper.lorebook_info_to_get_response(result)


@router.get(
    "/me/{lorebook_id}/entries",
    response_model=schemas.ListLorebookEntriesResponseDto,
)
async def list_my_lorebook_entries(
    lorebook_id: UUID,
    request: EntryListRequest,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.ListLorebookEntriesResponseDto:
    cursor = LorebookSchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        result = await query.list_lorebook_entries_by_owner_id(
            session,
            lorebook_id=lorebook_id,
            owner_id=owner_id,
            cursor=cursor,
            limit=request.limit,
        )
        if result is None:
            raise LookupError("Lorebook not found.")
    return LorebookSchemaMapper.entry_page_to_response(result)


@router.get(
    "/me/{lorebook_id}/entries/{entry_id}",
    response_model=schemas.GetLorebookEntryResponseDto,
)
async def get_my_lorebook_entry(
    lorebook_id: UUID,
    entry_id: UUID,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.GetLorebookEntryResponseDto:
    with _service_errors():
        result = await query.get_lorebook_entry_by_owner_id(
            session,
            lorebook_id=lorebook_id,
            entry_id=entry_id,
            owner_id=owner_id,
        )
        if result is None:
            raise LookupError("Lorebook entry not found.")
    return LorebookSchemaMapper.entry_info_to_get_response(result)


@router.get(
    "/{lorebook_id}",
    response_model=schemas.GetLorebookByIdResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def get_lorebook(
    lorebook_id: UUID,
    session: SessionDependency,
) -> schemas.GetLorebookByIdResponseDto:
    with _service_errors():
        result = await query.get_lorebook_by_id(session, lorebook_id=lorebook_id)
        if result is None:
            raise LookupError("Lorebook not found.")
    return LorebookSchemaMapper.lorebook_info_to_get_response(result)


@router.get(
    "/{lorebook_id}/entries",
    response_model=schemas.ListLorebookEntriesResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def list_entries(
    lorebook_id: UUID,
    request: EntryListRequest,
    session: SessionDependency,
) -> schemas.ListLorebookEntriesResponseDto:
    cursor = LorebookSchemaMapper.cursor_request_to_value(request)
    with _service_errors():
        parent = await query.get_lorebook_by_id(session, lorebook_id=lorebook_id)
        if parent is None:
            raise LookupError("Lorebook not found.")
        result = await query.list_lorebook_entries(
            session,
            lorebook_id=lorebook_id,
            cursor=cursor,
            limit=request.limit,
        )
    return LorebookSchemaMapper.entry_page_to_response(result)


@router.get(
    "/{lorebook_id}/entries/{entry_id}",
    response_model=schemas.GetLorebookEntryResponseDto,
    dependencies=[Depends(require_lorebook_admin)],
)
async def get_entry(
    lorebook_id: UUID,
    entry_id: UUID,
    session: SessionDependency,
) -> schemas.GetLorebookEntryResponseDto:
    with _service_errors():
        result = await query.get_lorebook_entry(
            session,
            lorebook_id=lorebook_id,
            entry_id=entry_id,
        )
        if result is None:
            raise LookupError("Lorebook entry not found.")
    return LorebookSchemaMapper.entry_info_to_get_response(result)


@router.post(
    "",
    response_model=schemas.CreateLorebookResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_lorebook(
    request: schemas.CreateLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.CreateLorebookResponseDto:
    value = LorebookSchemaMapper.create_lorebook_request_to_command(
        request,
        owner_id,
    )
    with _service_errors():
        result = await command.create_lorebook(session, value)
    return LorebookSchemaMapper.lorebook_info_to_create_response(result)


@router.put("", response_model=schemas.UpdateLorebookResponseDto)
async def update_lorebook(
    request: schemas.UpdateLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.UpdateLorebookResponseDto:
    value = LorebookSchemaMapper.update_lorebook_request_to_command(
        request,
        owner_id,
    )
    with _service_errors():
        result = await command.update_lorebook(session, value)
    return LorebookSchemaMapper.lorebook_info_to_update_response(result)


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
    # This mirrors the current character contract and still requires ownership.
    # A cross-owner moderator workflow needs a separate command and audit policy.
    value = LorebookSchemaMapper.change_lorebook_status_request_to_command(
        request,
        owner_id,
    )
    with _service_errors():
        result = await command.change_lorebook_status(session, value)
    return LorebookSchemaMapper.lorebook_info_to_status_response(result)


@router.delete("", response_model=schemas.DeleteLorebookResponseDto)
async def delete_lorebook(
    request: schemas.DeleteLorebookRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.DeleteLorebookResponseDto:
    value = LorebookSchemaMapper.delete_lorebook_request_to_command(
        request,
        owner_id,
    )
    with _service_errors():
        await command.delete_lorebook(session, value)
    return LorebookSchemaMapper.delete_lorebook_result_to_response(None)


@router.post(
    "/entries",
    response_model=schemas.CreateLorebookEntryResponseDto,
    status_code=status.HTTP_201_CREATED,
)
async def create_lorebook_entry(
    request: schemas.CreateLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.CreateLorebookEntryResponseDto:
    value = LorebookSchemaMapper.create_entry_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.create_lorebook_entry(session, value)
    return LorebookSchemaMapper.entry_info_to_create_response(result)


@router.put("/entries", response_model=schemas.UpdateLorebookEntryResponseDto)
async def update_lorebook_entry(
    request: schemas.UpdateLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.UpdateLorebookEntryResponseDto:
    value = LorebookSchemaMapper.update_entry_request_to_command(request, owner_id)
    with _service_errors():
        result = await command.update_lorebook_entry(session, value)
    return LorebookSchemaMapper.entry_info_to_update_response(result)


@router.delete("/entries", response_model=schemas.DeleteLorebookEntryResponseDto)
async def delete_lorebook_entry(
    request: schemas.DeleteLorebookEntryRequestDto,
    owner_id: OwnerDependency,
    session: SessionDependency,
) -> schemas.DeleteLorebookEntryResponseDto:
    value = LorebookSchemaMapper.delete_entry_request_to_command(request, owner_id)
    with _service_errors():
        await command.delete_lorebook_entry(session, value)
    return LorebookSchemaMapper.delete_entry_result_to_response(None)
