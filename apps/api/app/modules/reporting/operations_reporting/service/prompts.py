"""Administrator HTTP reporting uses chat public services/types exclusively."""

from app.core.reporting import get_reporting_period
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.query import prompts as ChatPromptsQueryService
from app.modules.reporting.operations_reporting import types as Types
from app.modules.reporting.operations_reporting.mapper import (
    prompts as PromptsPersistenceMapper,
)
from app.modules.reporting.operations_reporting.service.views import _require_actor


async def list_generation_prompts(
    session, command: Types.ListGenerationPromptsCommand, *, actor: Types.ActorCommand
) -> Types.GenerationPromptPageView:
    """활성 관리자에게 서울 날짜 범위·대화·상태 필터로 원문 없는 페이지를 제공한다."""
    with session.no_autoflush:
        await _require_actor(session, actor)
        period = get_reporting_period(command.date_from, command.date_to)
        if command.page < 1 or not 1 <= command.page_size <= 100:
            raise Types.ReportError("invalid_input")
        info = await ChatPromptsQueryService.list_generation_prompts(
            session,
            ChatTypes.ListGenerationPromptsCommand(
                actor_id=actor.user_id,
                start=period.start,
                end=period.end,
                conversation_id=command.conversation_id,
                status=command.status,
                limit=command.page_size,
                offset=(command.page - 1) * command.page_size,
            ),
        )
        return PromptsPersistenceMapper.generation_prompt_page_info_to_view(
            info, command
        )


async def get_generation_prompt(
    session, command: Types.GetGenerationPromptCommand, *, actor: Types.ActorCommand
) -> Types.GenerationPromptDetailView:
    """실패 생성도 조회하며 원문 미기록과 생성 미존재를 구분한다."""
    with session.no_autoflush:
        await _require_actor(session, actor)
        try:
            info = await ChatPromptsQueryService.get_generation_prompt(
                session,
                ChatTypes.GetGenerationPromptCommand(
                    actor.user_id, command.generation_id
                ),
            )
        except LookupError as exc:
            raise Types.ReportError("not_found") from exc
        return PromptsPersistenceMapper.generation_prompt_detail_info_to_view(info)
