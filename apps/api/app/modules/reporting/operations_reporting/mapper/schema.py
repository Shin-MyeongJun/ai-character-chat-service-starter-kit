"""Pure HTTP DTO/Command/View conversion."""

from dataclasses import asdict
from uuid import UUID

from app.modules.reporting.operations_reporting import schemas as Schemas
from app.modules.reporting.operations_reporting import types as Types


def generation_prompt_request_to_command(request) -> Types.ListGenerationPromptsCommand:
    """목록 HTTP 필터를 업무 조회 입력으로 변환한다."""
    return Types.ListGenerationPromptsCommand(**request.model_dump())


def generation_prompt_id_to_command(
    generation_id: UUID,
) -> Types.GetGenerationPromptCommand:
    """상세 식별자를 업무 조회 입력으로 변환한다."""
    return Types.GetGenerationPromptCommand(generation_id)


def generation_prompt_page_view_to_response(
    view,
) -> Schemas.GenerationPromptPageResponseDto:
    """원문 없는 목록 값을 응답 DTO로 변환한다."""
    return Schemas.GenerationPromptPageResponseDto(**asdict(view))


def generation_prompt_detail_view_to_response(
    view,
) -> Schemas.GenerationPromptDetailResponseDto:
    """상세 원문 값을 응답 DTO로 변환한다."""
    return Schemas.GenerationPromptDetailResponseDto(**asdict(view))
