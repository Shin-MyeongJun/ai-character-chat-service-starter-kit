"""Select only the public chat facts allowed in administrator prompt reporting."""

from app.modules.chatting.chat import types as ChatTypes
from app.modules.reporting.operations_reporting import types as Types


def generation_summary_info_to_view(
    info: ChatTypes.GenerationPromptSummaryInfo,
) -> Types.GenerationPromptSummaryView:
    """원문을 포함하지 않은 생성 메타데이터를 운영 조회 값으로 변환한다."""
    return Types.GenerationPromptSummaryView(
        generation_id=info.generation_id,
        conversation_id=info.conversation_id,
        model_id=info.model_id,
        model_name=info.model_name,
        reasoning_effort=info.reasoning_effort,
        status=info.status,
        created_at=info.created_at,
        finished_at=info.finished_at,
        history_invalidated_at=info.history_invalidated_at,
        prompt_recorded=info.prompt_recorded,
        prompt_created_at=info.prompt_created_at,
        provider=info.provider,
    )


def generation_prompt_page_info_to_view(
    info: ChatTypes.GenerationPromptPageInfo,
    command: Types.ListGenerationPromptsCommand,
) -> Types.GenerationPromptPageView:
    """목록과 페이지 정보를 원문 없는 운영 조회 값으로 조합한다."""
    return Types.GenerationPromptPageView(
        tuple(generation_summary_info_to_view(item) for item in info.items),
        info.total,
        command.page,
        command.page_size,
    )


def generation_prompt_detail_info_to_view(
    info: ChatTypes.GenerationPromptDetailInfo,
) -> Types.GenerationPromptDetailView:
    """기록 유무와 저장된 원문을 그대로 상세 값으로 변환한다."""
    prompt = (
        None
        if info.prompt is None
        else Types.GenerationPromptView(
            request_json=info.prompt.request_json,
            digest=info.prompt.digest,
            format_version=info.prompt.format_version,
            created_at=info.prompt.created_at,
            provider=info.prompt.provider,
            max_output_tokens=info.prompt.max_output_tokens,
        )
    )
    return Types.GenerationPromptDetailView(
        generation_summary_info_to_view(info.generation), prompt
    )
