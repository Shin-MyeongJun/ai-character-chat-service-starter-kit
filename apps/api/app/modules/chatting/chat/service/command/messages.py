# 메시지 저장·교체·되돌리기의 소유권과 대화 잠금을 관리한다. 실제 생성 출력은 generation.py에서 저장한다.
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


# 사용자 입력 저장의 공개 경계다. 소유 대화를 잠그고 요청 키 영수증과 현재 생성 상태를 확인한다.
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
        # 삭제 후에도 receipt는 남는다. 본문 digest나 원본 revision이 다르면 재생성하지 않고 충돌 처리한다.
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


# 마지막 사용자 메시지의 예상 revision이 일치할 때만 같은 ID/position으로 내용을 교체한다.
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
        # 교체와 같은 트랜잭션에서 대화 기억 전체를 무효화한다. 생성 비용·통계 사실은 되돌리지 않는다.
        await _invalidate_history(session, command)
        row = await Repository.replace_message(session, target.id, command.content)
        result = PersistenceMapper.message_entity_to_info(row)
        assert result is not None
        return result


# 대상 position을 포함한 뒤쪽 이력을 삭제한다. 대화 버전은 유지하고 기억은 무효화한다.
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
