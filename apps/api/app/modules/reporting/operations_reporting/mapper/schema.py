"""Pure HTTP DTO/Command/View conversion."""

from uuid import UUID

from app.modules.reporting.operations_reporting import schemas as Schemas
from app.modules.reporting.operations_reporting import types as Types


def generation_prompt_request_to_command(
    request: Schemas.ListGenerationPromptsRequestDto,
) -> Types.ListGenerationPromptsCommand:
    """목록 HTTP 필터를 업무 조회 입력으로 변환한다."""
    return Types.ListGenerationPromptsCommand(
        date_from=request.date_from,
        date_to=request.date_to,
        conversation_id=request.conversation_id,
        status=request.status,
        page=request.page,
        page_size=request.page_size,
    )


def generation_prompt_id_to_command(
    generation_id: UUID,
) -> Types.GetGenerationPromptCommand:
    """상세 식별자를 업무 조회 입력으로 변환한다."""
    return Types.GetGenerationPromptCommand(generation_id)


def generation_prompt_page_view_to_response(
    view: Types.GenerationPromptPageView,
) -> Schemas.GenerationPromptPageResponseDto:
    """원문 없는 목록 값을 응답 DTO로 변환한다."""
    return Schemas.GenerationPromptPageResponseDto(
        items=[_generation_summary_view_to_response(item) for item in view.items],
        total=view.total,
        page=view.page,
        page_size=view.page_size,
    )


def generation_prompt_detail_view_to_response(
    view: Types.GenerationPromptDetailView,
) -> Schemas.GenerationPromptDetailResponseDto:
    """상세 원문 값을 응답 DTO로 변환한다."""
    return Schemas.GenerationPromptDetailResponseDto(
        generation=_generation_summary_view_to_response(view.generation),
        prompt=(
            None
            if view.prompt is None
            else Schemas.GenerationPromptResponseDto(
                request_json=view.prompt.request_json,
                digest=view.prompt.digest,
                format_version=view.prompt.format_version,
                created_at=view.prompt.created_at,
                provider=view.prompt.provider,
                max_output_tokens=view.prompt.max_output_tokens,
            )
        ),
    )


def _generation_summary_view_to_response(
    view: Types.GenerationPromptSummaryView,
) -> Schemas.GenerationPromptSummaryResponseDto:
    """목록·상세가 공유하는 원문 없는 메타데이터만 HTTP로 변환한다."""
    return Schemas.GenerationPromptSummaryResponseDto(
        generation_id=view.generation_id,
        conversation_id=view.conversation_id,
        model_id=view.model_id,
        model_name=view.model_name,
        reasoning_effort=view.reasoning_effort,
        status=view.status,
        created_at=view.created_at,
        finished_at=view.finished_at,
        history_invalidated_at=view.history_invalidated_at,
        prompt_recorded=view.prompt_recorded,
        prompt_created_at=view.prompt_created_at,
        provider=view.provider,
    )
