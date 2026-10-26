"""Select only the public chat facts allowed in administrator prompt reporting."""

from dataclasses import fields

from app.modules.reporting.operations_reporting import types as Types


def generation_summary_info_to_view(info) -> Types.GenerationPromptSummaryView:
    """원문을 포함하지 않은 생성 메타데이터를 운영 조회 값으로 변환한다."""
    return Types.GenerationPromptSummaryView(
        **{
            field.name: getattr(info, field.name)
            for field in fields(Types.GenerationPromptSummaryView)
        }
    )


def generation_prompt_page_info_to_view(
    info, command
) -> Types.GenerationPromptPageView:
    """목록과 페이지 정보를 원문 없는 운영 조회 값으로 조합한다."""
    return Types.GenerationPromptPageView(
        tuple(generation_summary_info_to_view(item) for item in info.items),
        info.total,
        command.page,
        command.page_size,
    )


def generation_prompt_detail_info_to_view(info) -> Types.GenerationPromptDetailView:
    """기록 유무와 저장된 원문을 그대로 상세 값으로 변환한다."""
    prompt = (
        None
        if info.prompt is None
        else Types.GenerationPromptView(
            **{
                field.name: getattr(info.prompt, field.name)
                for field in fields(Types.GenerationPromptView)
            }
        )
    )
    return Types.GenerationPromptDetailView(
        generation_summary_info_to_view(info.generation), prompt
    )
