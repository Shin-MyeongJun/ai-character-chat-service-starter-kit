from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.db.models.chat import Message, MessageRequest
from app.db.models.product_usage import ProductGeneration


async def has_pending_generation(session, conversation_id) -> bool:
    return (
        await session.scalar(
            select(ProductGeneration.id)
            .where(
                ProductGeneration.conversation_id == conversation_id,
                ProductGeneration.status == "pending",
            )
            .limit(1)
        )
        is not None
    )


async def get_message(session, conversation_id, message_id):
    return await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.id == message_id)
        .execution_options(populate_existing=True)
    )


async def get_last_message(session, conversation_id):
    return await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.position.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )


async def list_messages(session, conversation_id, after, limit):
    return list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.position > after)
            .order_by(Message.position)
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    )


async def list_message_range(session, conversation_id, after, through, limit):
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.position > after
    )
    if through is not None:
        stmt = stmt.where(Message.position <= through)
    return list(
        await session.scalars(
            stmt.order_by(Message.position)
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    )


async def get_message_request(session, conversation_id, request_key):
    return await session.get(
        MessageRequest, (conversation_id, request_key), populate_existing=True
    )


async def create_message(
    session,
    command,
    snapshot_id,
    sender_type,
    character_id,
    product_character_id,
    digest,
):
    message = Message(
        conversation_id=command.conversation_id,
        content=command.content,
        sender_type=sender_type,
        character_id=character_id,
        product_character_id=product_character_id,
        product_snapshot_id=snapshot_id,
        generated_by_ai=False,
    )
    session.add(message)
    await session.flush()
    session.add(
        MessageRequest(
            conversation_id=command.conversation_id,
            request_key=command.request_key,
            input_digest=digest,
            message_id=message.id,
        )
    )
    await session.flush()
    return message


async def replace_message(session, message_id, content):
    return await session.scalar(
        update(Message)
        .where(Message.id == message_id)
        .values(
            content=content,
            revision=Message.revision + 1,
            generation_id=None,
            generated_by_ai=False,
            model_id=None,
            token_count=None,
            emotion_tag=None,
        )
        .returning(Message)
        .execution_options(populate_existing=True)
    )


async def delete_messages_from(session, conversation_id, position) -> int:
    result = await session.execute(
        delete(Message).where(
            Message.conversation_id == conversation_id, Message.position >= position
        )
    )
    return result.rowcount


async def invalidate_generation_history(session, conversation_id, now) -> None:
    # Execution counters/digests are immutable historical facts. Mark that their
    # original context is no longer the live history, without changing billing.
    await session.execute(
        update(ProductGeneration)
        .where(
            ProductGeneration.conversation_id == conversation_id,
            ProductGeneration.history_invalidated_at.is_(None),
        )
        .values(history_invalidated_at=now)
    )


async def get_generation_by_request(session, user_id, request_key):
    return await session.scalar(
        select(ProductGeneration).where(
            ProductGeneration.user_id == user_id,
            ProductGeneration.request_key == request_key,
        )
    )


async def get_owned_generation(session, generation_id, user_id, *, lock=False):
    stmt = (
        select(ProductGeneration)
        .where(
            ProductGeneration.id == generation_id, ProductGeneration.user_id == user_id
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def create_generation(
    session,
    conversation,
    execution,
    user_id,
    request_key,
    digest,
    input_text,
    input_message_id=None,
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
    if input_message_id is not None:
        return run
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


async def update_answer(session, generation_id, metadata, lease_until):
    await session.execute(
        update(ProductGeneration)
        .where(ProductGeneration.id == generation_id)
        .values(answer_metadata=metadata, answer_lease_until=lease_until)
    )


async def list_expired_answers(session, now, limit):
    return list(
        await session.scalars(
            select(ProductGeneration)
            .where(
                ProductGeneration.status == "pending",
                ProductGeneration.answer_lease_until <= now,
            )
            .order_by(ProductGeneration.answer_lease_until)
            .limit(limit)
        )
    )


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
    return generations, users
