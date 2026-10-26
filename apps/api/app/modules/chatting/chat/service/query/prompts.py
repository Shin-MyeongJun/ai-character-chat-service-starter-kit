"""Admin-only original prompt facts. No HTTP or provider credential access."""

from app.core.reporting import validate_reporting_times
from app.modules.chatting.chat import repository as PromptsRepository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import prompts as PromptsPersistenceMapper
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def list_generation_prompts(
    session, command: Types.ListGenerationPromptsCommand
) -> Types.GenerationPromptPageInfo:
    """활성 관리자에게 원문 없는 생성 목록을 생성 시각 [start,end)로 제공한다."""
    with session.no_autoflush:
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        validate_reporting_times(command.start, command.end)
        if (
            not 1 <= command.limit <= 100
            or command.offset < 0
            or command.status
            not in (None, "pending", "succeeded", "failed", "cancelled", "stale")
        ):
            raise ValueError("Invalid generation prompt filters.")
        rows, total = await PromptsRepository.list_generation_prompts(
            session,
            start=command.start,
            end=command.end,
            conversation_id=command.conversation_id,
            status=command.status,
            limit=command.limit,
            offset=command.offset,
        )
        return PromptsPersistenceMapper.generation_prompt_rows_to_page(rows, total)


async def get_generation_prompt(
    session, command: Types.GetGenerationPromptCommand
) -> Types.GenerationPromptDetailInfo:
    """미존재 생성은 오류, 과거 원문 미기록 생성은 prompt=None으로 구별한다."""
    with session.no_autoflush:
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        generation = PromptsPersistenceMapper.generation_prompt_row_to_summary(
            await PromptsRepository.get_generation_prompt_summary(
                session, command.generation_id
            )
        )
        if generation is None:
            raise LookupError("Generation not found.")
        prompt = PromptsPersistenceMapper.prompt_entity_to_info(
            await PromptsRepository.get_generation_prompt(
                session, command.generation_id
            )
        )
        return Types.GenerationPromptDetailInfo(generation, prompt)
