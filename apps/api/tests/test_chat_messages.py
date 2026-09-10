"""Real PostgreSQL tests for message ownership, locking and historical facts."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from app.db.models.billing import CreditAccount, CreditTransaction, Payment, UsageLog
from app.db.models.chat import (
    Conversation,
    ConversationCharacter,
    ConversationVersionChange,
    Message,
    MessageRequest,
)
from app.db.models.memory import ConversationMemory
from app.db.models.product_usage import ProductGeneration, ProductPaymentEvent
from app.db.transaction import use_case_transaction
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import messages as CommandService
from app.modules.chatting.chat.service.command.generation import (
    begin_generation,
    finish_generation,
)
from app.modules.chatting.chat.service.query.messages import list_messages
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.command.versions import switch_version
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service.command.attribution import record_sale
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.releases import publish_product
from app.use_cases.conversations import start_conversation
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_usage import scenario

pytestmark = pytest.mark.asyncio


def create(cid, uid, key="user", content="Hello"):
    return Types.CreateMessageCommand(
        conversation_id=cid, user_id=uid, request_key=key, content=content
    )


def edit(message, uid, content="Edited"):
    return Types.ReplaceMessageCommand(
        conversation_id=message.conversation_id,
        user_id=uid,
        message_id=message.id,
        expected_revision=message.revision,
        content=content,
    )


def rewind(message, uid):
    return Types.RewindMessagesCommand(
        conversation_id=message.conversation_id, user_id=uid, message_id=message.id
    )


async def history(db, cid, uid, **kwargs):
    async with db.begin():
        return await list_messages(
            db, Types.ListMessagesCommand(conversation_id=cid, user_id=uid, **kwargs)
        )


async def run_generation(db, cid, uid, character):
    command = Types.BeginGenerationCommand(
        conversation_id=cid,
        user_id=uid,
        request_key="generation",
        input_text="Generate",
    )
    run = await begin_generation(db, command)
    finish = Types.FinishGenerationCommand(
        generation_id=run.id,
        user_id=uid,
        value=Types.GenerationResult(
            12, 7, 3, (Types.GeneratedMessage(character, "Original generated output"),)
        ),
    )
    await finish_generation(db, finish)
    return run, command, finish


async def test_owner_message_and_character_scope(db):
    owner, product, _release, cid, character = await scenario(db)
    other = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(
            product_id=product.id, user_id=owner.id
        ),
    )
    message = await CommandService.create_message(db, create(cid, owner.id))
    for action, command in (
        (CommandService.create_message, create(cid, uuid4())),
        (CommandService.replace_message, edit(message, uuid4())),
        (CommandService.rewind_messages, rewind(message, uuid4())),
        (
            CommandService.replace_message,
            replace(edit(message, owner.id), conversation_id=other.id),
        ),
        (
            CommandService.rewind_messages,
            replace(rewind(message, owner.id), conversation_id=other.id),
        ),
    ):
        with pytest.raises(LookupError):
            await action(db, command)
    with pytest.raises(LookupError):
        await history(db, cid, uuid4())
    with pytest.raises(ValueError, match="participant"):
        await CommandService.create_character_message(
            db,
            Types.CreateCharacterMessageCommand(
                conversation_id=cid,
                user_id=owner.id,
                request_key="bad-character",
                content="Bad",
                product_character_id=uuid4(),
            ),
        )
    internal = await CommandService.create_character_message(
        db,
        Types.CreateCharacterMessageCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="internal",
            content="Character",
            product_character_id=character,
        ),
    )
    assert internal.sender_type == "character" and not internal.generated_by_ai
    with pytest.raises(Types.MessagePermissionError):
        await CommandService.replace_message(db, edit(internal, owner.id))
    with pytest.raises(Types.MessagePermissionError):
        await CommandService.replace_character_message(
            db,
            Types.ReplaceCharacterMessageCommand(
                **{
                    **{
                        f: getattr(edit(message, owner.id), f)
                        for f in edit(message, owner.id).__dataclass_fields__
                    },
                    "product_character_id": character,
                }
            ),
        )


async def test_order_pages_timestamp_ties_and_deleted_cursor(db):
    owner, _p, _r, cid, _c = await scenario(db)
    saved = [
        await CommandService.create_message(db, create(cid, owner.id, str(i), str(i)))
        for i in range(5)
    ]
    async with db.begin():
        await db.execute(
            update(Message)
            .where(Message.conversation_id == cid)
            .values(created_at=datetime(2026, 1, 1, tzinfo=UTC))
        )
    cursor, found = None, []
    while True:
        page = await history(db, cid, owner.id, cursor=cursor, limit=2)
        found.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert [m.id for m in found[1:]] == [m.id for m in saved]
    assert len({m.id for m in found}) == 6
    assert [m.position for m in found] == sorted(m.position for m in found)
    with pytest.raises(ValueError, match="cursor"):
        await history(
            db, cid, owner.id, cursor=Types.MessageCursor(uuid4(), saved[0].position)
        )
    with pytest.raises(ValueError, match="limit"):
        await history(db, cid, owner.id, limit=0)
    cursor = Types.MessageCursor(cid, saved[2].position)
    result = await CommandService.rewind_messages(db, rewind(saved[2], owner.id))
    assert result.deleted_count == 3
    new = await CommandService.create_message(db, create(cid, owner.id, "after", "New"))
    page = await history(db, cid, owner.id, cursor=cursor)
    assert [m.id for m in page.items] == [new.id]


async def test_concurrent_create_retry_conflict_and_tombstone(db):
    owner, _p, _r, cid, _c = await scenario(db)
    command = create(cid, owner.id)

    async def save():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await CommandService.create_message(session, command)

    results = await asyncio.gather(*(save() for _ in range(5)))
    assert len({m.id for m in results}) == 1
    assert len((await history(db, cid, owner.id)).items) == 2
    with pytest.raises(Types.MessageConflictError, match="different input"):
        await CommandService.create_message(db, replace(command, content="different"))
    await CommandService.rewind_messages(db, rewind(results[0], owner.id))
    with pytest.raises(Types.MessageConflictError, match="deleted"):
        await CommandService.create_message(db, command)
    async with db.begin():
        receipt = await db.get(MessageRequest, (cid, command.request_key))
        assert receipt.message_id is None


async def test_last_only_and_concurrent_revision(db):
    owner, _p, _r, cid, _c = await scenario(db)
    first = await CommandService.create_message(db, create(cid, owner.id))
    last = await CommandService.create_message(db, create(cid, owner.id, "last"))
    with pytest.raises(Types.MessageConflictError, match="last message"):
        await CommandService.replace_message(db, edit(first, owner.id))

    async def change(content):
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await CommandService.replace_message(
                session, edit(last, owner.id, content)
            )

    results = await asyncio.gather(change("A"), change("B"), return_exceptions=True)
    successes = [r for r in results if isinstance(r, Types.MessageInfo)]
    assert len(successes) == 1 and successes[0].revision == 2
    assert sum(isinstance(r, Types.MessageConflictError) for r in results) == 1
    with pytest.raises(Types.MessageConflictError, match="replaced"):
        await CommandService.create_message(db, create(cid, owner.id, "last"))


async def test_pending_blocks_writes_and_distinct_generation(db):
    owner, _p, _r, cid, _character = await scenario(db)
    message = await CommandService.create_message(db, create(cid, owner.id))
    begin = Types.BeginGenerationCommand(
        conversation_id=cid, user_id=owner.id, request_key="run", input_text="Input"
    )
    run = await begin_generation(db, begin)
    for action, command in (
        (CommandService.create_message, create(cid, owner.id, "later")),
        (CommandService.replace_message, edit(message, owner.id)),
        (CommandService.rewind_messages, rewind(message, owner.id)),
        (begin_generation, replace(begin, request_key="another")),
    ):
        with pytest.raises(Types.MessageConflictError, match="progress"):
            await action(db, command)
    assert (await begin_generation(db, begin)).id == run.id
    await finish_generation(
        db,
        Types.FinishGenerationCommand(
            generation_id=run.id,
            user_id=owner.id,
            value=Types.GenerationResult(0, 0, 0, outcome="cancelled"),
        ),
    )
    await CommandService.rewind_messages(db, rewind(message, owner.id))


@pytest.mark.parametrize("operation", ["replace", "rewind"])
@pytest.mark.parametrize("first", ["generation", "mutation"])
async def test_generation_and_mutation_serialize_both_lock_orders(db, operation, first):
    owner, _p, _r, cid, _c = await scenario(db)
    message = await CommandService.create_message(db, create(cid, owner.id))
    begin = Types.BeginGenerationCommand(
        conversation_id=cid, user_id=owner.id, request_key="run", input_text="Input"
    )
    locked, release = asyncio.Event(), asyncio.Event()

    async def act(session, name):
        if name == "generation":
            return await begin_generation(session, begin)
        if operation == "replace":
            return await CommandService.replace_message(
                session, edit(message, owner.id)
            )
        return await CommandService.rewind_messages(session, rewind(message, owner.id))

    async def holder():
        async with (
            AsyncSession(db.bind, expire_on_commit=False) as session,
            use_case_transaction(session),
        ):
            result = await act(session, first)
            locked.set()
            await asyncio.wait_for(release.wait(), 5)
            return result

    async def waiter():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await act(
                session, "mutation" if first == "generation" else "generation"
            )

    task1 = asyncio.create_task(holder())
    await asyncio.wait_for(locked.wait(), 5)
    task2 = asyncio.create_task(waiter())
    try:
        done, _ = await asyncio.wait({task2}, timeout=0.1)
        assert not done, "Second writer must wait for the conversation row lock"
    finally:
        release.set()
    results = await asyncio.wait_for(
        asyncio.gather(task1, task2, return_exceptions=True), 5
    )
    assert not isinstance(results[0], Exception)
    if first == "generation":
        assert isinstance(results[1], Types.MessageConflictError)
    else:
        assert isinstance(results[1], Types.GenerationInfo)
    page = await history(db, cid, owner.id)
    assert page.items[-1].content == "Input"
    if first == "mutation" and operation == "rewind":
        assert message.id not in {m.id for m in page.items}


async def test_correction_and_rewind_preserve_execution_usage_and_version(db):
    owner, product, release, cid, character = await scenario(db)
    other = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(
            product_id=product.id, user_id=owner.id
        ),
    )
    run, begin, finish = await run_generation(db, cid, owner.id, character)
    output = (await history(db, cid, owner.id)).items[-1]
    payment_id = uuid4()
    async with db.begin():
        db.add(
            Payment(
                id=payment_id,
                user_id=owner.id,
                amount=Decimal("100.00"),
                currency="KRW",
                status="succeeded",
                pg_provider="test",
            )
        )
        db.add(CreditAccount(user_id=owner.id, balance=97))
        db.add(
            CreditTransaction(
                user_id=owner.id,
                amount=-3,
                reason="chat_usage",
                reference_id=run.id,
                idempotency_key="historical-debit",
            )
        )
        db.add(
            ConversationMemory(
                conversation_id=cid,
                memory_type="summary",
                content="Old",
                source_message_id=output.id,
            )
        )
        db.add(
            ConversationMemory(
                conversation_id=cid,
                memory_type="fact",
                content="Legacy unknown provenance",
            )
        )
        db.add(
            ConversationMemory(
                conversation_id=other.id,
                memory_type="fact",
                content="Other conversation remains",
            )
        )
        usage = await db.scalar(
            select(UsageLog).where(UsageLog.generation_id == run.id)
        )
        usage_values = (
            usage.id,
            usage.input_tokens,
            usage.output_tokens,
            usage.cost_credit,
            usage.product_snapshot_id,
        )
        stored = await db.get(ProductGeneration, run.id)
        generation_values = (
            stored.status,
            stored.result_digest,
            stored.message_count,
            stored.finished_at,
        )
    sale = await record_sale(
        db,
        BillingTypes.RecordSaleCommand(
            payment_id=payment_id,
            snapshot_id=release.snapshot_id,
            event_key="chat-preservation",
            amount=Decimal("100.00"),
            occurred_at=datetime.now(UTC),
        ),
    )
    correction = await CommandService.replace_character_message(
        db,
        Types.ReplaceCharacterMessageCommand(
            conversation_id=cid,
            user_id=owner.id,
            message_id=output.id,
            expected_revision=1,
            product_character_id=character,
            content="Corrected output",
        ),
    )
    assert (
        correction.generation_id is None
        and correction.model_id is None
        and not correction.generated_by_ai
    )
    latest = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=product.id,
            owner_id=owner.id,
            value=ProductTypes.ReleaseNoteCommand("Next", "Media update", True),
        ),
    )
    await switch_version(
        db,
        ConversationTypes.SwitchVersionCommand(
            conversation_id=cid, user_id=owner.id, target_snapshot_id=latest.snapshot_id
        ),
    )
    page = await history(db, cid, owner.id)
    assert (
        await CommandService.rewind_messages(db, rewind(page.items[1], owner.id))
    ).deleted_count == 2
    assert (await begin_generation(db, begin)).id == run.id
    assert (await finish_generation(db, finish)).id == run.id
    assert len((await history(db, cid, owner.id)).items) == 1
    async with db.begin():
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ConversationMemory)
                .where(ConversationMemory.conversation_id == cid)
            )
            == 0
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ConversationMemory)
                .where(ConversationMemory.conversation_id == other.id)
            )
            == 1
        )
        stored = await db.get(ProductGeneration, run.id, populate_existing=True)
        assert stored.history_invalidated_at is not None
        assert (
            stored.status,
            stored.result_digest,
            stored.message_count,
            stored.finished_at,
        ) == generation_values
        usage = await db.scalar(
            select(UsageLog).where(UsageLog.generation_id == run.id)
        )
        assert (
            usage.id,
            usage.input_tokens,
            usage.output_tokens,
            usage.cost_credit,
            usage.product_snapshot_id,
        ) == usage_values
        room = await db.get(Conversation, cid, populate_existing=True)
        assert (
            room.product_snapshot_id == latest.snapshot_id
            and room.initial_snapshot_id == release.snapshot_id
        )
        assert (
            await db.scalar(select(func.count()).select_from(ConversationVersionChange))
            == 1
        )
        payment = await db.get(Payment, payment_id)
        assert payment.status == "succeeded" and payment.amount == Decimal("100.00")
        attribution = await db.get(ProductPaymentEvent, sale.id)
        assert attribution.payment_id == payment_id and attribution.amount == Decimal(
            "100.00"
        )
        assert attribution.product_snapshot_id == release.snapshot_id
        assert (await db.get(CreditAccount, owner.id)).balance == 97
        debit = await db.scalar(
            select(CreditTransaction).where(CreditTransaction.reference_id == run.id)
        )
        assert debit.amount == -3 and debit.idempotency_key == "historical-debit"


async def test_memory_failure_rolls_back_history_and_opening_failure_rolls_back_room(
    db, monkeypatch
):
    owner, product, _release, cid, character = await scenario(db)
    run, _begin, _finish = await run_generation(db, cid, owner.id, character)
    message = await CommandService.create_message(db, create(cid, owner.id))
    async with db.begin():
        db.add(
            ConversationMemory(
                conversation_id=cid,
                memory_type="event",
                content="Keep",
                source_message_id=message.id,
            )
        )
    original = CommandService.invalidate_conversation_memories

    async def fail(session, command):
        await original(session, command)
        raise RuntimeError("Simulated failure")

    monkeypatch.setattr(CommandService, "invalidate_conversation_memories", fail)
    with pytest.raises(RuntimeError, match="Simulated"):
        await CommandService.rewind_messages(db, rewind(message, owner.id))
    async with db.begin():
        assert await db.get(Message, message.id) is not None
        assert (
            await db.scalar(select(func.count()).select_from(ConversationMemory)) == 1
        )
        assert (await db.get(ProductGeneration, run.id)).history_invalidated_at is None
    from app.use_cases import conversations

    async def fail_opening(session, command):
        raise RuntimeError("Opening failure")

    monkeypatch.setattr(conversations, "create_character_message", fail_opening)
    with pytest.raises(RuntimeError, match="Opening"):
        await start_conversation(
            db,
            ConversationTypes.StartConversationCommand(
                product_id=product.id, user_id=owner.id
            ),
        )
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(Conversation)) == 1


async def test_generation_checks_actual_participants(db):
    owner, _product, _release, cid, character = await scenario(db)
    run = await begin_generation(
        db,
        Types.BeginGenerationCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="nonparticipant",
            input_text="Input",
        ),
    )
    async with db.begin():
        # Same published version, but no longer in this room's participants.
        from sqlalchemy import delete

        await db.execute(
            delete(ConversationCharacter).where(
                ConversationCharacter.conversation_id == cid
            )
        )
    with pytest.raises(ValueError, match="character"):
        await finish_generation(
            db,
            Types.FinishGenerationCommand(
                generation_id=run.id,
                user_id=owner.id,
                value=Types.GenerationResult(
                    1, 1, 1, (Types.GeneratedMessage(character, "Bad"),)
                ),
            ),
        )
    async with db.begin():
        assert (await db.get(ProductGeneration, run.id)).status == "pending"
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 0
