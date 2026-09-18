# 대화 ID와 user_id를 함께 조회해 미소유·미존재를 같은 LookupError로 처리한다.
# lock=True는 쓰기 조율용이다. 이 함수 자체는 상품 버전 가용성을 검사하지 않는다.
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper


async def get_owned_conversation(
    session, command: Types.OwnedConversationCommand
) -> Types.ConversationInfo:
    conversation_id = command.conversation_id
    user_id = command.user_id
    lock = command.lock
    row = await Repository.get_owned_conversation(
        session, conversation_id, user_id, lock=lock
    )
    info = PersistenceMapper.conversation_entity_to_info(row)
    if info is None:
        raise LookupError("Conversation not found.")
    return info


async def get_statistics_facts(
    session, command: Types.GetStatisticsFactsCommand
) -> Types.ConversationStatisticsInfo:
    rows = await Repository.get_statistics_facts(
        session, command.product_id, command.start, command.end
    )
    return PersistenceMapper.conversation_statistics_rows_to_info(rows)


async def list_conversation_characters(
    session, command: Types.OwnedConversationCommand
) -> tuple[Types.ConversationCharacterInfo, ...]:
    await get_owned_conversation(session, command)
    rows = await Repository.list_conversation_characters(
        session, command.conversation_id
    )
    return PersistenceMapper.conversation_characters_entities_to_infos(rows)
