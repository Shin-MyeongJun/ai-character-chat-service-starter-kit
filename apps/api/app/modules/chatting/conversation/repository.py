from uuid import uuid4

from sqlalchemy import delete, func, select

from app.db.models.chat import (
    Conversation,
    ConversationCharacter,
    ConversationVersionChange,
    Message,
)
from app.db.models.product_usage import ProductGeneration


async def get_owned_conversation(session, conversation_id, user_id, *, lock=False):
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(stmt)


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
    session.add(
        Message(
            conversation_id=conversation.id,
            sender_type="character",
            character_id=command.primary_character_id,
            product_character_id=command.primary_product_character_id,
            product_snapshot_id=command.snapshot_id,
            content=command.opening_message,
            generated_by_ai=False,
        )
    )
    await session.flush()
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


async def get_generation_by_request(session, user_id, request_key):
    return await session.scalar(
        select(ProductGeneration).where(
            ProductGeneration.user_id == user_id,
            ProductGeneration.request_key == request_key,
        )
    )


async def get_owned_generation(session, generation_id, user_id):
    return await session.scalar(
        select(ProductGeneration)
        .where(
            ProductGeneration.id == generation_id, ProductGeneration.user_id == user_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def create_generation(
    session, conversation, execution, user_id, request_key, digest, input_text
):
    run = ProductGeneration(
        id=uuid4(),
        user_id=user_id,
        conversation_id=conversation.id,
        product_id=conversation.product_id,
        product_snapshot_id=conversation.product_snapshot_id,
        model_id=execution.model_id,
        model_name=execution.model,
        reasoning_effort=execution.reasoning_effort,
        request_key=request_key,
        input_digest=digest,
        status="pending",
        message_count=0,
    )
    session.add(run)
    await session.flush()
    session.add(
        Message(
            conversation_id=conversation.id,
            product_snapshot_id=run.product_snapshot_id,
            generation_id=run.id,
            sender_type="user",
            content=input_text,
            generated_by_ai=False,
        )
    )
    await session.flush()
    return run


async def add_generation_message(session, run, output, character_id) -> None:
    session.add(
        Message(
            conversation_id=run.conversation_id,
            product_snapshot_id=run.product_snapshot_id,
            generation_id=run.id,
            product_character_id=output.product_character_id,
            character_id=character_id,
            sender_type="character",
            content=output.content,
            model_id=run.model_id,
            generated_by_ai=True,
        )
    )
    await session.flush()


async def finish_generation(
    session, generation_id, status, fingerprint, now, message_count
):
    run = await session.get(ProductGeneration, generation_id)
    run.status, run.result_digest, run.finished_at = status, fingerprint, now
    run.message_count = message_count
    await session.flush()
    return run


async def get_statistics_facts(session, product_id, start, end):
    g = ProductGeneration
    generations = list(
        await session.execute(
            select(
                g.product_snapshot_id, g.status, func.count(), func.sum(g.message_count)
            )
            .where(
                g.product_id == product_id, g.finished_at >= start, g.finished_at < end
            )
            .group_by(g.product_snapshot_id, g.status)
        )
    )
    users = list(
        await session.execute(
            select(g.product_snapshot_id, g.user_id)
            .where(
                g.product_id == product_id,
                g.status == "succeeded",
                g.finished_at >= start,
                g.finished_at < end,
            )
            .distinct()
        )
    )
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
    return generations, users, conversations, transitions
