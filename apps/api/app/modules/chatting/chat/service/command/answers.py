"""Persistence boundary for the top-level nonstream answer use case."""

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes


async def get_answer_request(
    session, command: Types.GetAnswerRequestCommand
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
    session, command: Types.GetAnswerInputCommand
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


async def update_answer(session, command: Types.UpdateAnswerCommand) -> None:
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
        await Repository.update_answer(
            session, info.id, command.metadata, command.lease_until
        )


async def list_expired_answers(
    session, command: Types.ListExpiredAnswersCommand
) -> tuple[Types.GenerationStateInfo, ...]:
    if not 1 <= command.limit <= 100:
        raise ValueError("Invalid recovery batch size.")
    return tuple(
        PersistenceMapper.generation_entity_to_state_info(row)
        for row in await Repository.list_expired_answers(
            session, command.now, command.limit
        )
    )
