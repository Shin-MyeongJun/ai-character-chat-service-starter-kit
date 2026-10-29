# AnswerOrchestrator의 영속 경계. 사용자 요청 키 잠금 → 대화 잠금 순으로 중복 요청을
# 직렬화한다.
"""Persistence boundary for the top-level nonstream answer use case."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes


async def get_answer_request(
    session: AsyncSession, command: Types.GetAnswerRequestCommand
) -> Types.GenerationStateInfo | None:
    # Caller composes this lock with runtime preparation and reservation.
    async with use_case_transaction(session):
        await lock_key(
            session, "generation", f"{command.user_id}:{command.request_key}"
        )
        await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=command.conversation_id,
                user_id=command.user_id,
                lock=True,
            ),
        )
        return PersistenceMapper.generation_entity_to_state_info(
            await Repository.get_generation_by_request(
                session, command.user_id, command.request_key
            )
        )


async def get_answer_input(
    session: AsyncSession, command: Types.GetAnswerInputCommand
) -> Types.MessageInfo:
    await ConversationService.get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    info = PersistenceMapper.message_entity_to_info(
        await Repository.get_last_message(session, command.conversation_id)
    )
    if (
        info is None
        or info.id != command.message_id
        or info.sender_type != "user"
        or info.revision != command.expected_revision
    ):
        raise Types.MessageConflictError(
            "Input must reference the last user message and revision."
        )
    return info


async def update_answer(
    session: AsyncSession, command: Types.UpdateAnswerCommand
) -> None:
    async with use_case_transaction(session):
        info = PersistenceMapper.generation_entity_to_state_info(
            await Repository.get_owned_generation(
                session, command.generation_id, command.user_id
            )
        )
        if info is None:
            raise LookupError("Generation not found.")
        await ConversationService.get_owned_conversation(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=info.conversation_id, user_id=command.user_id, lock=True
            ),
        )
        info = PersistenceMapper.generation_entity_to_state_info(
            await Repository.get_owned_generation(
                session, command.generation_id, command.user_id, lock=True
            )
        )
        if info is None or info.status != "pending":
            raise Types.MessageConflictError("Generation is already terminal.")
        stored = info.answer_metadata or {}
        token = stored.get("execution_token")
        if token is not None:
            if command.execution_token != token:
                raise Types.MessageConflictError("Answer execution ownership was lost.")
            expired = (
                info.answer_lease_until is None
                or info.answer_lease_until <= datetime.now(UTC)
            )
            if expired != command.recover:
                raise Types.MessageConflictError("Answer execution lease changed.")
            if any(
                stored.get(key) != command.metadata.get(key)
                for key in (
                    "execution_token",
                    "identity",
                    "billing",
                    "preparation_digest",
                    "prompt_digest",
                    "estimated_prompt_tokens",
                    "response_tokens",
                    "token_estimator",
                    "template",
                    "provider",
                    "version",
                )
            ):
                raise Types.MessageConflictError(
                    "Answer execution snapshot is immutable."
                )
            if stored.get("phase") == "result_ready":
                if stored != command.metadata:
                    raise Types.MessageConflictError("A durable result already exists.")
                return
        await Repository.update_answer(
            session, info.id, command.metadata, command.lease_until
        )


async def list_expired_answers(
    session: AsyncSession, command: Types.ListExpiredAnswersCommand
) -> tuple[Types.GenerationStateInfo, ...]:
    if not 1 <= command.limit <= 100:
        raise ValueError("Invalid recovery batch size.")
    return tuple(
        PersistenceMapper.generation_entity_to_state_info(generation_entity)
        for generation_entity in await Repository.list_expired_answers(
            session, command.now, command.limit
        )
    )
