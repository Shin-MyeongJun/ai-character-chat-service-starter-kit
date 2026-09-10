import hashlib
import json
from datetime import UTC, datetime

from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import (
    get_owned_conversation,
    list_conversation_characters,
)
from app.modules.chatting.memory import types as MemoryTypes
from app.modules.chatting.memory.service import invalidate_conversation_memories


def _validate_content(content):
    if not content.strip() or len(content) > 200000:
        raise ValueError("Message must contain 1–200000 nonblank characters.")


async def _lock_conversation(session, command):
    return await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id, lock=True
        ),
    )


async def _ensure_idle(session, conversation_id):
    if await Repository.has_pending_generation(session, conversation_id):
        raise Types.MessageConflictError("A generation is in progress.")


async def _get_character(session, command):
    participants = await list_conversation_characters(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    character = next(
        (
            c
            for c in participants
            if c.product_character_id == command.product_character_id
        ),
        None,
    )
    if character is None:
        raise ValueError("Character is not a participant in this conversation version.")
    return character


async def create_message(
    session, command: Types.CreateMessageCommand
) -> Types.MessageInfo:
    return await _create_message(session, command, character=False)


async def create_character_message(
    session, command: Types.CreateCharacterMessageCommand
) -> Types.MessageInfo:
    return await _create_message(session, command, character=True)


async def _create_message(session, command, *, character):
    _validate_content(command.content)
    if not command.request_key.strip() or len(command.request_key) > 128:
        raise ValueError("Invalid message request key.")
    sender_type = "character" if character else "user"
    product_character_id = command.product_character_id if character else None
    digest = hashlib.sha256(
        json.dumps([sender_type, str(product_character_id), command.content]).encode()
    ).hexdigest()
    async with use_case_transaction(session):
        conversation = await _lock_conversation(session, command)
        row = await Repository.get_message_request(
            session, command.conversation_id, command.request_key
        )
        receipt = PersistenceMapper.message_request_entity_to_info(row)
        if receipt:
            if receipt.input_digest != digest:
                raise Types.MessageConflictError(
                    "Request key was used with different input."
                )
            row = await Repository.get_message(
                session, command.conversation_id, receipt.message_id
            )
            existing = PersistenceMapper.message_entity_to_info(row)
            if existing is None or existing.revision != 1:
                raise Types.MessageConflictError(
                    "The original message was replaced or deleted."
                )
            return existing
        await _ensure_idle(session, command.conversation_id)
        participant = await _get_character(session, command) if character else None
        row = await Repository.create_message(
            session,
            command,
            conversation.product_snapshot_id,
            sender_type,
            participant.character_id if participant else None,
            product_character_id,
            digest,
        )
        result = PersistenceMapper.message_entity_to_info(row)
        assert result is not None
        return result


async def replace_message(
    session, command: Types.ReplaceMessageCommand
) -> Types.MessageInfo:
    return await _replace_message(session, command, character=False)


async def replace_character_message(
    session, command: Types.ReplaceCharacterMessageCommand
) -> Types.MessageInfo:
    return await _replace_message(session, command, character=True)


async def _replace_message(session, command, *, character):
    _validate_content(command.content)
    if type(command.expected_revision) is not int or command.expected_revision < 1:
        raise ValueError("Invalid expected revision.")
    async with use_case_transaction(session):
        conversation = await _lock_conversation(session, command)
        await _ensure_idle(session, command.conversation_id)
        row = await Repository.get_message(
            session, command.conversation_id, command.message_id
        )
        target = PersistenceMapper.message_entity_to_info(row)
        if target is None:
            raise LookupError("Message not found.")
        if target.sender_type != ("character" if character else "user"):
            raise Types.MessagePermissionError(
                "This command cannot replace that sender's message."
            )
        if character:
            await _get_character(session, command)
            if (
                target.product_character_id != command.product_character_id
                or target.product_snapshot_id != conversation.product_snapshot_id
            ):
                raise ValueError(
                    "Message does not belong to this character and version."
                )
        row = await Repository.get_last_message(session, command.conversation_id)
        last = PersistenceMapper.message_entity_to_info(row)
        if last is None or last.id != target.id:
            raise Types.MessageConflictError("Only the last message can be replaced.")
        if target.revision != command.expected_revision:
            raise Types.MessageConflictError("Message revision has changed.")
        await _invalidate_history(session, command)
        row = await Repository.replace_message(session, target.id, command.content)
        result = PersistenceMapper.message_entity_to_info(row)
        assert result is not None
        return result


async def rewind_messages(
    session, command: Types.RewindMessagesCommand
) -> Types.RewindMessagesInfo:
    async with use_case_transaction(session):
        await _lock_conversation(session, command)
        await _ensure_idle(session, command.conversation_id)
        row = await Repository.get_message(
            session, command.conversation_id, command.message_id
        )
        target = PersistenceMapper.message_entity_to_info(row)
        if target is None:
            raise LookupError("Message not found.")
        await _invalidate_history(session, command)
        count = await Repository.delete_messages_from(
            session, command.conversation_id, target.position
        )
        return Types.RewindMessagesInfo(count)


async def _invalidate_history(session, command):
    await invalidate_conversation_memories(
        session,
        MemoryTypes.InvalidateConversationMemoriesCommand(
            conversation_id=command.conversation_id, owner_id=command.user_id
        ),
    )
    await Repository.invalidate_generation_history(
        session, command.conversation_id, datetime.now(UTC)
    )
