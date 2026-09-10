import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.db.models.billing import Payment, UsageLog
from app.db.models.chat import Message
from app.db.models.product_usage import ProductGeneration, ProductPaymentEvent
from app.db.models.snapshot.product import ProductSnapshotCharacter
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.chat.service.command.generation import (
    begin_generation,
    finish_generation,
)
from app.modules.chatting.chat.types import GeneratedMessage, GenerationResult
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service.command.versions import switch_version
from app.modules.commerce.billing import types as BillingTypes
from app.modules.commerce.billing.service.command.attribution import (
    record_refund,
    record_sale,
)
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.command.releases import publish_product
from app.modules.content.product.types import ReleaseNoteCommand
from app.use_cases.conversations import start_conversation
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_integration import ready_product

pytestmark = pytest.mark.asyncio


async def scenario(db):
    owner, _c, _b, p, _model, _entry = await ready_product(db)
    release = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("First", "First"),
        ),
    )
    conversation = await start_conversation(
        db,
        ConversationTypes.StartConversationCommand(product_id=p.id, user_id=owner.id),
    )
    async with db.begin():
        character_id = await db.scalar(
            select(ProductSnapshotCharacter.id).where(
                ProductSnapshotCharacter.product_snapshot_id == release.snapshot_id
            )
        )
    return (owner, p, release, conversation.id, character_id)


async def test_concurrent_generation_retries_and_atomic_usage(db):
    owner, p, release, cid, character_id = await scenario(db)

    async def reserve():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await begin_generation(
                session,
                ChatTypes.BeginGenerationCommand(
                    conversation_id=cid,
                    user_id=owner.id,
                    request_key="turn-1",
                    input_text="Hello",
                ),
            )

    a, b = await asyncio.gather(reserve(), reserve())
    assert a.id == b.id and sum(r.created for r in (a, b)) == 1
    output = GenerationResult(
        100,
        30,
        7,
        (
            GeneratedMessage(character_id, "Hi"),
            GeneratedMessage(character_id, "Welcome"),
        ),
    )

    async def finish():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await finish_generation(
                session,
                ChatTypes.FinishGenerationCommand(
                    generation_id=a.id, user_id=owner.id, value=output
                ),
            )

    first, second = await asyncio.gather(finish(), finish())
    assert first.status == second.status == "succeeded"
    async with db.begin():
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 2
        )
        usage = await db.scalar(select(UsageLog))
        assert (
            usage.product_id == p.id
            and usage.product_snapshot_id == release.snapshot_id
        )
        assert usage.input_tokens == 100 and usage.reasoning_effort == "low"
    with pytest.raises(ValueError, match="different input"):
        await begin_generation(
            db,
            ChatTypes.BeginGenerationCommand(
                conversation_id=cid,
                user_id=owner.id,
                request_key="turn-1",
                input_text="Different",
            ),
        )
    with pytest.raises(ValueError, match="different output"):
        await finish_generation(
            db,
            ChatTypes.FinishGenerationCommand(
                generation_id=a.id,
                user_id=owner.id,
                value=GenerationResult(100, 30, 8, output.messages),
            ),
        )


async def test_stale_generation_retains_cost_and_old_version(db):
    owner, p, release, cid, character_id = await scenario(db)
    run = await begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="turn",
            input_text="Hello",
        ),
    )
    latest = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Media", "Media", True),
        ),
    )
    await switch_version(
        db,
        ConversationTypes.SwitchVersionCommand(
            conversation_id=cid, user_id=owner.id, target_snapshot_id=latest.snapshot_id
        ),
    )
    result = await finish_generation(
        db,
        ChatTypes.FinishGenerationCommand(
            generation_id=run.id,
            user_id=owner.id,
            value=GenerationResult(
                12, 3, 2, (GeneratedMessage(character_id, "Old response"),)
            ),
        ),
    )
    assert result.status == "stale" and result.message_count == 0
    async with db.begin():
        usage = await db.scalar(select(UsageLog))
        assert (
            usage.product_snapshot_id == release.snapshot_id and usage.cost_credit == 2
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 0
        )


async def test_generation_validation_rolls_back_and_can_be_retried(db):
    owner, _p, _release, cid, character_id = await scenario(db)
    run = await begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="turn",
            input_text="Hello",
        ),
    )
    with pytest.raises(ValueError, match="character"):
        await finish_generation(
            db,
            ChatTypes.FinishGenerationCommand(
                generation_id=run.id,
                user_id=owner.id,
                value=GenerationResult(
                    1,
                    1,
                    1,
                    (
                        GeneratedMessage(character_id, "valid"),
                        GeneratedMessage(uuid4(), "wrong product"),
                    ),
                ),
            ),
        )
    async with db.begin():
        assert (await db.get(ProductGeneration, run.id)).status == "pending"
        assert await db.scalar(select(func.count()).select_from(UsageLog)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(Message.generated_by_ai.is_(True))
            )
            == 0
        )
    await finish_generation(
        db,
        ChatTypes.FinishGenerationCommand(
            generation_id=run.id,
            user_id=owner.id,
            value=GenerationResult(1, 0, 1, outcome="failed"),
        ),
    )
    with pytest.raises(LookupError):
        await finish_generation(
            db,
            ChatTypes.FinishGenerationCommand(
                generation_id=run.id,
                user_id=uuid4(),
                value=GenerationResult(1, 0, 1, outcome="failed"),
            ),
        )


async def test_payment_partial_refunds_are_idempotent_and_version_pinned(db):
    owner, _p, release, _cid, _character_id = await scenario(db)
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
    when = datetime.now(UTC) - timedelta(days=20)
    sale = await record_sale(
        db,
        BillingTypes.RecordSaleCommand(
            payment_id=payment_id,
            snapshot_id=release.snapshot_id,
            event_key="sale",
            amount=Decimal(80),
            occurred_at=when,
        ),
    )
    assert sale == await record_sale(
        db,
        BillingTypes.RecordSaleCommand(
            payment_id=payment_id,
            snapshot_id=release.snapshot_id,
            event_key="sale",
            amount=Decimal(80),
            occurred_at=when,
        ),
    )
    with pytest.raises(ValueError, match="exceeds"):
        await record_sale(
            db,
            BillingTypes.RecordSaleCommand(
                payment_id=payment_id,
                snapshot_id=release.snapshot_id,
                event_key="overflow",
                amount=Decimal(30),
                occurred_at=when,
            ),
        )
    refund_time = datetime.now(UTC)

    async def refund():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            return await record_refund(
                session,
                BillingTypes.RecordRefundCommand(
                    sale_id=sale.id,
                    event_key="refund",
                    amount=Decimal(50),
                    occurred_at=refund_time,
                ),
            )

    a, b = await asyncio.gather(refund(), refund())
    assert a == b
    with pytest.raises(ValueError, match="exceeds"):
        await record_refund(
            db,
            BillingTypes.RecordRefundCommand(
                sale_id=sale.id,
                event_key="over-refund",
                amount=Decimal(31),
                occurred_at=refund_time,
            ),
        )
    async with db.begin():
        row = await db.get(ProductPaymentEvent, a.id)
        assert (
            row.product_snapshot_id == release.snapshot_id and row.attributed_at == when
        )
        assert (
            await db.scalar(select(func.count()).select_from(ProductPaymentEvent)) == 2
        )
