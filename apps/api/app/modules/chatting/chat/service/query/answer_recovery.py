"""Owner-scoped operational history without provider results or investigation text."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat.service.query import generation as GenerationQueryService


async def list_answer_recovery_attempts(
    session: AsyncSession, command: Types.GetGenerationStateCommand
) -> tuple[Types.AnswerRecoveryAttemptInfo, ...]:
    await GenerationQueryService.get_generation_state(session, command)
    return tuple(
        PersistenceMapper.answer_recovery_attempt_entity_to_info(entity)
        for entity in await Repository.list_answer_recovery_attempts(
            session, command.generation_id
        )
    )
