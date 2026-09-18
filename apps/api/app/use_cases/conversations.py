# 대화 시작 API의 최상위 트랜잭션. 방·참여자 생성과 opening 메시지 저장을 함께 확정한다.
"""Atomic room creation and opening message; domain modules never call back here."""

from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.command.messages import create_character_message
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.command import (
    create_product_conversation,
)


async def start_conversation(
    session, command: ConversationTypes.StartConversationCommand
) -> ConversationTypes.ConversationStartedInfo:
    async with use_case_transaction(session):
        prepared = await create_product_conversation(session, command)
        await create_character_message(
            session,
            ChatTypes.CreateCharacterMessageCommand(
                conversation_id=prepared.conversation.id,
                user_id=command.user_id,
                request_key="opening",
                content=prepared.opening_message,
                product_character_id=prepared.product_character_id,
            ),
        )
        return prepared.conversation
