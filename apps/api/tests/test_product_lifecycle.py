import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.db.models.identity import User
from app.db.models.memory import ConversationMemory
from app.db.models.model_routing import Model, ModelReplacement
from app.db.models.product import Product
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.chatting.conversation.service import runtime_context
from app.modules.content.product.service.notices import (
    pending_updates,
    version_availability,
)
from app.modules.content.product.service.releases import publish
from app.modules.content.product.types import ReleasePublish
from app.modules.governance.admin.product_policy import set_expiry
from app.modules.llm.replacement import announce_retirement, resolve_execution
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_product_usage import scenario

pytestmark = pytest.mark.asyncio


async def test_concurrent_publication_serializes_versions_and_refreshes_cached_product(
    db,
):
    owner, p, _release, _cid, _charid = await scenario(db)

    async def publish_once():
        async with AsyncSession(db.bind, expire_on_commit=False) as session:
            # Simulate a reused session that cached the old latest version.
            async with session.begin():
                await session.get(Product, p.id)
            return await publish(
                session,
                product_id=p.id,
                owner_id=owner.id,
                value=ReleasePublish("Concurrent", "Concurrent"),
            )

    a, b = await asyncio.gather(publish_once(), publish_once())
    assert sorted([a.version, b.version]) == [2, 3]
    async with db.begin():
        product = await db.scalar(
            select(Product)
            .where(Product.id == p.id)
            .execution_options(populate_existing=True)
        )
        assert (await db.get(ProductSnapshot, product.latest_snapshot_id)).version == 3


async def test_expiry_blocks_execution_but_preserves_memory(db):
    owner, _p, release, cid, _charid = await scenario(db)
    async with db.begin():
        actor = await db.get(User, owner.id)
        actor.role = "admin"
        db.add(
            ConversationMemory(
                conversation_id=cid, memory_type="fact", content="Remember me"
            )
        )
    await set_expiry(
        db,
        snapshot_id=release.snapshot_id,
        actor_id=owner.id,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        reason="Grace period ended",
    )
    async with db.begin():
        with pytest.raises(ValueError, match="expired"):
            await runtime_context(db, conversation_id=cid, user_id=owner.id)
        memory = await db.scalar(
            select(ConversationMemory).where(ConversationMemory.conversation_id == cid)
        )
        assert memory.content == "Remember me"


async def test_model_retirement_plans_before_deadline_and_switches_once(db):
    owner, p, release, cid, _charid = await scenario(db)
    replacement_id = uuid4()
    now = datetime.now(UTC)
    async with db.begin():
        actor = await db.get(User, owner.id)
        actor.role = "admin"
        snapshot = await db.get(ProductSnapshot, release.snapshot_id)
        original_id = UUID(snapshot.snapshot_data["model"]["id"])
        original = await db.get(Model, original_id)
        db.add(
            Model(
                id=replacement_id,
                provider_id=original.provider_id,
                model_name="model-v2",
                display_name="v2",
                context_window=32000,
                input_price=1,
                output_price=1,
                capabilities={
                    "model_family": "test",
                    "reasoning_efforts": ["low", "high"],
                },
            )
        )
    shutdown = now + timedelta(days=2)
    await announce_retirement(
        db,
        actor_id=owner.id,
        model_id=original_id,
        announced_at=now - timedelta(days=1),
        shutdown_at=shutdown,
    )
    async with db.begin():
        customer = await pending_updates(db, conversation_id=cid, user_id=owner.id)
        creator = await version_availability(
            db, product_id=p.id, snapshot_id=release.snapshot_id, owner_id=owner.id
        )
        assert customer.model_notice == creator.model_notice
        assert customer.model_notice.state == "scheduled"
        assert customer.model_notice.replacement_model_id == replacement_id
        assert await db.scalar(select(func.count()).select_from(ModelReplacement)) == 0
        with pytest.raises(LookupError):
            await version_availability(
                db, product_id=p.id, snapshot_id=release.snapshot_id, owner_id=uuid4()
            )
        planned = await resolve_execution(db, snapshot_id=release.snapshot_id, now=now)
        assert (
            planned.model_id == original_id
            and planned.planned_model_id == replacement_id
        )
        assert planned.scheduled_at == shutdown - timedelta(days=1)
    async with db.begin():
        executed = await resolve_execution(
            db, snapshot_id=release.snapshot_id, now=shutdown - timedelta(days=1)
        )
        assert executed.model_id == replacement_id and executed.replacement
        assert await db.scalar(select(func.count()).select_from(ModelReplacement)) == 1
        assert (await db.get(ProductSnapshot, release.snapshot_id)).snapshot_data[
            "model"
        ]["id"] == str(original_id)
