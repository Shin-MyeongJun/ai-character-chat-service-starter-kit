"""Only prompt list/detail reporting is HTTP-exposed; active admin is checked by services."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.reporting import ReportingError
from app.http.dependencies import Owner, Session
from app.modules.reporting.operations_reporting import schemas as Schemas
from app.modules.reporting.operations_reporting import types as Types
from app.modules.reporting.operations_reporting.mapper import schema as SchemaMapper
from app.modules.reporting.operations_reporting.service import prompts as PromptsService

router = APIRouter(
    prefix="/admin/reporting/generation-prompts", tags=["operations reporting"]
)


@contextmanager
def _report_errors() -> Iterator[None]:
    """업무 실패를 원문 없는 고정 HTTP 오류로 변환한다."""
    try:
        yield
    except ReportingError as exc:
        status = {"forbidden": 403, "not_found": 404}.get(exc.code, 422)
        raise HTTPException(status, exc.code) from exc
    except ValueError as exc:
        raise HTTPException(422, "invalid_input") from exc


@router.get("", response_model=Schemas.GenerationPromptPageResponseDto)
async def list_generation_prompts(
    query: Annotated[Schemas.ListGenerationPromptsRequestDto, Query()],
    session: Session,
    owner: Owner,
    response: Response,
) -> Schemas.GenerationPromptPageResponseDto:
    """관리자 목록 요청을 변환하고 민감 응답의 캐시를 막는다."""
    response.headers["Cache-Control"] = "no-store"
    with _report_errors():
        view = await PromptsService.list_generation_prompts(
            session,
            SchemaMapper.generation_prompt_request_to_command(query),
            actor=Types.ActorCommand(owner),
        )
        return SchemaMapper.generation_prompt_page_view_to_response(view)


@router.get(
    "/{generation_id}", response_model=Schemas.GenerationPromptDetailResponseDto
)
async def get_generation_prompt(
    generation_id: UUID,
    session: Session,
    owner: Owner,
    response: Response,
) -> Schemas.GenerationPromptDetailResponseDto:
    """관리자에게 지정 생성의 저장 원문만 상세 조회로 반환한다."""
    response.headers["Cache-Control"] = "no-store"
    with _report_errors():
        view = await PromptsService.get_generation_prompt(
            session,
            SchemaMapper.generation_prompt_id_to_command(generation_id),
            actor=Types.ActorCommand(owner),
        )
        return SchemaMapper.generation_prompt_detail_view_to_response(view)
