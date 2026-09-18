# 서울 날짜 경계, 상태별 집계, 통화별 매출·환불 및 기간 사용자 중복 제거를 확인한다.
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.db.models.billing import Payment, UsageLog
from app.db.models.product_statistics import (
    ProductStatsDirtyDay,
    ProductVersionDailyStats,
)
from app.db.models.product_usage import ProductGeneration
from app.db.models.snapshot.product import ProductSnapshotCharacter
from app.db.product_stats_queue import day_bounds, statistics_day
from app.db.transaction import use_case_transaction
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
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)
from app.modules.content.product.service.query.statistics import get_statistics
from app.modules.content.product.types import ReleaseNoteCommand
from app.use_cases import product_statistics as StatisticsCommandService
from app.use_cases import product_statistics as statistics
from sqlalchemy import func, select, update
from test_product_usage import scenario


def test_seoul_day_boundary():
    assert statistics_day(datetime(2026, 9, 8, 14, 59, 59, tzinfo=UTC)) == date(
        2026, 9, 8
    )
    assert statistics_day(datetime(2026, 9, 8, 15, tzinfo=UTC)) == date(2026, 9, 9)
    assert day_bounds(date(2026, 9, 9)) == (
        datetime(2026, 9, 8, 15, tzinfo=UTC),
        datetime(2026, 9, 9, 15, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_version_totals_unique_users_and_rebuild_are_correct(db):
    owner, p, _release, cid, charid = await scenario(db)
    first = await begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="first",
            input_text="First",
        ),
    )
    await finish_generation(
        db,
        ChatTypes.FinishGenerationCommand(
            generation_id=first.id,
            user_id=owner.id,
            value=GenerationResult(
                10,
                4,
                3,
                (GeneratedMessage(charid, "One"), GeneratedMessage(charid, "Two")),
            ),
        ),
    )
    latest = await publish_product(
        db,
        ProductTypes.PublishCommand(
            product_id=p.id,
            owner_id=owner.id,
            value=ReleaseNoteCommand("Next", "Media", True),
        ),
    )
    await switch_version(
        db,
        ConversationTypes.SwitchVersionCommand(
            conversation_id=cid, user_id=owner.id, target_snapshot_id=latest.snapshot_id
        ),
    )
    async with use_case_transaction(db):
        charid2 = await db.scalar(
            select(ProductSnapshotCharacter.id).where(
                ProductSnapshotCharacter.product_snapshot_id == latest.snapshot_id
            )
        )
    second = await begin_generation(
        db,
        ChatTypes.BeginGenerationCommand(
            conversation_id=cid,
            user_id=owner.id,
            request_key="second",
            input_text="Second",
        ),
    )
    await finish_generation(
        db,
        ChatTypes.FinishGenerationCommand(
            generation_id=second.id,
            user_id=owner.id,
            value=GenerationResult(7, 2, 1, (GeneratedMessage(charid2, "New"),)),
        ),
    )
    today = statistics_day(datetime.now(UTC))
    assert (
        await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    ).processed > 0
    async with use_case_transaction(db):
        report = await get_statistics(
            db,
            ProductTypes.GetStatisticsCommand(
                product_id=p.id, owner_id=owner.id, date_from=today, date_to=today
            ),
        )
        assert report.pending_days == []
        assert report.totals.active_users == 1
        assert report.totals.succeeded == 2 and report.totals.messages == 3
        assert report.totals.input_tokens == 17 and report.totals.cost_credit == 4
        assert report.totals.conversations == 1 and report.totals.transitions == 1
        versions = list(
            await db.scalars(
                select(ProductVersionDailyStats).where(
                    ProductVersionDailyStats.product_id == p.id
                )
            )
        )
        assert len(versions) == 2 and all(v.active_users == 1 for v in versions)
        await mark_statistics_dirty(
            db, ProductTypes.MarkStatisticsDirtyCommand(p.id, datetime.now(UTC))
        )
    await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    async with use_case_transaction(db):
        again = await get_statistics(
            db,
            ProductTypes.GetStatisticsCommand(
                product_id=p.id, owner_id=owner.id, date_from=today, date_to=today
            ),
        )
        assert again.totals == report.totals
        with pytest.raises(LookupError):
            await get_statistics(
                db,
                ProductTypes.GetStatisticsCommand(
                    product_id=p.id, owner_id=uuid4(), date_from=today, date_to=today
                ),
            )
    yesterday_start, _ = day_bounds(today - timedelta(days=1))
    async with use_case_transaction(db):
        await db.execute(
            update(ProductGeneration)
            .where(ProductGeneration.id == first.id)
            .values(finished_at=yesterday_start)
        )
        await db.execute(
            update(UsageLog)
            .where(UsageLog.generation_id == first.id)
            .values(created_at=yesterday_start)
        )
        await mark_statistics_dirty(
            db, ProductTypes.MarkStatisticsDirtyCommand(p.id, yesterday_start)
        )
        await mark_statistics_dirty(
            db, ProductTypes.MarkStatisticsDirtyCommand(p.id, datetime.now(UTC))
        )
    await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    async with use_case_transaction(db):
        period = await get_statistics(
            db,
            ProductTypes.GetStatisticsCommand(
                product_id=p.id,
                owner_id=owner.id,
                date_from=today - timedelta(days=1),
                date_to=today,
            ),
        )
        assert (
            period.totals.active_users == 1
            and sum(d.active_users for d in period.days) == 2
        )


@pytest.mark.asyncio
async def test_late_refund_rebuilds_original_day_and_keeps_currency_separate(db):
    owner, p, release, _cid, _charid = await scenario(db)
    now = datetime.now(UTC)
    old = now - timedelta(days=20)
    payment_ids = [uuid4(), uuid4()]
    async with use_case_transaction(db):
        for pid, currency in zip(payment_ids, ("KRW", "USD"), strict=True):
            db.add(
                Payment(
                    id=pid,
                    user_id=owner.id,
                    amount=Decimal(100),
                    currency=currency,
                    status="succeeded",
                    pg_provider="test",
                )
            )
    sale = await record_sale(
        db,
        BillingTypes.RecordSaleCommand(
            payment_id=payment_ids[0],
            snapshot_id=release.snapshot_id,
            event_key="krw",
            amount=Decimal(80),
            occurred_at=old,
        ),
    )
    await record_sale(
        db,
        BillingTypes.RecordSaleCommand(
            payment_id=payment_ids[1],
            snapshot_id=release.snapshot_id,
            event_key="usd",
            amount=Decimal(20),
            occurred_at=old,
        ),
    )
    await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    await record_refund(
        db,
        BillingTypes.RecordRefundCommand(
            sale_id=sale.id, event_key="late", amount=Decimal(30), occurred_at=now
        ),
    )
    async with use_case_transaction(db):
        dirty = await db.get(ProductStatsDirtyDay, (p.id, statistics_day(old)))
        assert dirty is not None
    await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    async with use_case_transaction(db):
        report = await get_statistics(
            db,
            ProductTypes.GetStatisticsCommand(
                product_id=p.id,
                owner_id=owner.id,
                date_from=statistics_day(old),
                date_to=statistics_day(now),
            ),
        )
        assert Decimal(report.totals.revenue["KRW"].net) == 50
        assert Decimal(report.totals.revenue["USD"].net) == 20
        assert report.totals.revenue["KRW"].sale_count == 1
        assert report.totals.revenue["KRW"].refund_count == 1


@pytest.mark.asyncio
async def test_failed_aggregation_leaves_queue_for_retry(db, monkeypatch):
    _owner, p, _release, _cid, _charid = await scenario(db)
    original = statistics.rebuild_day

    async def fail(*args, **kwargs):
        raise RuntimeError("temporary aggregation failure")

    monkeypatch.setattr(StatisticsCommandService, "rebuild_day", fail)
    with pytest.raises(RuntimeError):
        await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    async with use_case_transaction(db):
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProductStatsDirtyDay)
                .where(ProductStatsDirtyDay.product_id == p.id)
            )
            == 1
        )
    monkeypatch.setattr(StatisticsCommandService, "rebuild_day", original)
    assert (
        await statistics.process_pending(db, ProductTypes.ProcessPendingCommand())
    ).processed == 1
