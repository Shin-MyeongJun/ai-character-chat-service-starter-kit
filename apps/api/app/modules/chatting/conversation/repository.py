from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db.models.chat import (
    Conversation,
    ConversationCharacter,
    ConversationVersionChange,
)


async def get_owned_conversation(session, conversation_id, user_id, *, lock=False):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def list_conversation_characters(session, conversation_id):
    return list(
        await session.scalars(
            select(ConversationCharacter)
            .where(ConversationCharacter.conversation_id == conversation_id)
            .order_by(ConversationCharacter.role_order, ConversationCharacter.id)
        )
    )


async def create_conversation(session, command):
    conversation = Conversation(
        id=uuid4(),
        user_id=command.user_id,
        product_id=command.product_id,
        product_snapshot_id=command.snapshot_id,
        initial_snapshot_id=command.snapshot_id,
        start_set_id=command.start_set_id,
        is_group=len(command.characters) > 1,
        title=command.title,
    )
    session.add(conversation)
    await session.flush()
    for c in command.characters:
        session.add(
            ConversationCharacter(
                conversation_id=conversation.id,
                character_id=c.character_id,
                product_character_id=c.product_character_id,
                role_order=c.role_order,
            )
        )
    return conversation


async def switch_conversation_version(
    session, conversation_id, current_id, target_id, characters, mode, changed_at
) -> None:
    conversation = await session.get(Conversation, conversation_id)
    await session.execute(
        delete(ConversationCharacter).where(
            ConversationCharacter.conversation_id == conversation_id
        )
    )
    for c in characters:
        session.add(
            ConversationCharacter(
                conversation_id=conversation_id,
                character_id=c.character_id,
                product_character_id=c.product_character_id,
                role_order=c.role_order,
            )
        )
    session.add(
        ConversationVersionChange(
            created_at=changed_at,
            conversation_id=conversation_id,
            from_snapshot_id=current_id,
            to_snapshot_id=target_id,
            mode=mode,
        )
    )
    conversation.product_snapshot_id = target_id
    conversation.is_group = len(characters) > 1
    conversation.active_model_id = None
    await session.flush()


async def get_statistics_facts(session, product_id, start, end):
    conversations = list(
        await session.execute(
            select(Conversation.initial_snapshot_id, func.count())
            .where(
                Conversation.product_id == product_id,
                Conversation.initial_snapshot_id.is_not(None),
                Conversation.created_at >= start,
                Conversation.created_at < end,
            )
            .group_by(Conversation.initial_snapshot_id)
        )
    )
    c = ConversationVersionChange
    transitions = list(
        await session.execute(
            select(c.to_snapshot_id, func.count())
            .join(Conversation, Conversation.id == c.conversation_id)
            .where(
                Conversation.product_id == product_id,
                c.created_at >= start,
                c.created_at < end,
            )
            .group_by(c.to_snapshot_id)
        )
    )
    return conversations, transitions
