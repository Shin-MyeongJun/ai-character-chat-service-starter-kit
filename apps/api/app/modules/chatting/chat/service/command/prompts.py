"""Persist one final prompt within the generation reservation transaction."""

import hashlib
from datetime import UTC, datetime

from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import repository as PromptsRepository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.chat.mapper import prompts as PromptsPersistenceMapper
from app.modules.chatting.conversation import service as ConversationService
from app.modules.chatting.conversation import types as ConversationTypes


async def save_generation_prompt(
    session, command: Types.SaveGenerationPromptCommand
) -> None:
    """실행권과 예약을 확인해 원문을 한 번 저장한다. 실패하면 예약 전체가 롤백된다."""
    async with use_case_transaction(session):
        info = PersistenceMapper.generation_entity_to_state_info(
            await PromptsRepository.get_owned_generation(
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
            await PromptsRepository.get_owned_generation(
                session, command.generation_id, command.user_id, lock=True
            )
        )
        metadata = info.answer_metadata or {}
        digest = hashlib.sha256(command.request_json.encode("utf-8")).hexdigest()
        if (
            not command.execution_token
            or metadata.get("execution_token") != command.execution_token
            or metadata.get("prompt_digest") != digest
            or metadata.get("provider") != command.provider
            or metadata.get("response_tokens") != command.max_output_tokens
        ):
            raise Types.MessageConflictError(
                "Prompt does not match reserved execution."
            )
        stored = PromptsPersistenceMapper.prompt_entity_to_info(
            await PromptsRepository.get_generation_prompt(
                session, command.generation_id
            )
        )
        if stored is not None:
            if (
                stored.request_json,
                stored.digest,
                stored.provider,
                stored.max_output_tokens,
            ) != (
                command.request_json,
                digest,
                command.provider,
                command.max_output_tokens,
            ):
                raise Types.MessageConflictError(
                    "Stored generation prompt is immutable."
                )
            return
        if (
            info.status != "pending"
            or metadata.get("phase") != "reserved"
            or info.answer_lease_until is None
            or info.answer_lease_until <= datetime.now(UTC)
        ):
            raise Types.MessageConflictError(
                "Prompt execution reservation is unavailable."
            )
        await PromptsRepository.create_generation_prompt(
            session,
            command.generation_id,
            request_json=command.request_json,
            digest=digest,
            format_version=1,
            provider=command.provider,
            max_output_tokens=command.max_output_tokens,
        )
