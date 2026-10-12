"""실제 PostgreSQL의 스코프·DISTINCT·버전·기간과 읽기 전용 계약을 검증한다."""

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.reporting import ReportingError, get_reporting_period
from app.db.models.billing import UsageLog
from app.db.models.identity import User
from app.db.models.model_routing import Model
from app.db.models.product import Product
from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)
from app.db.models.product_usage import ProductGeneration
from app.db.models.snapshot.product import ProductSnapshot
from app.modules.account_reporting import types as AccountTypes
from app.modules.account_reporting.service import views as AccountViewsService
from app.modules.creator_reporting import types as CreatorTypes
from app.modules.creator_reporting.service import views as CreatorViewsService
from app.modules.operations_reporting import types as OperationsTypes
from app.modules.operations_reporting.service import views as OperationsViewsService
from sqlalchemy import func, select, text
from test_product_usage import scenario


@asynccontextmanager
async def readonly(db):
    """준비 데이터 commit 후 DB 자체가 쓰기를 거절하는 새 조회 트랜잭션을 연다."""
    async with db.begin():
        await db.execute(text("SET TRANSACTION READ ONLY"))
        yield


async def seed_statistics(db):
    """현재 테스트 스키마에만 사용자·작품·버전의 알려진 집계를 준비한다."""
    owner, other, admin = [uuid4() for _ in range(3)]
    db.add_all(
        [
            User(id=owner, email=f"{owner}@example.test"),
            User(id=other, email=f"{other}@example.test"),
            User(id=admin, email=f"{admin}@example.test", role="admin"),
        ]
    )
    product_id, other_product, version, other_version = [uuid4() for _ in range(4)]
    db.add_all(
        [
            Product(id=product_id, owner_id=owner, title="작품"),
            Product(id=other_product, owner_id=other, title="다른 작품"),
        ]
    )
    await db.flush()
    db.add_all(
        [
            ProductSnapshot(
                id=version,
                product_id=product_id,
                version=1,
                snapshot_data={"title": "작품"},
            ),
            ProductSnapshot(
                id=other_version,
                product_id=other_product,
                version=1,
                snapshot_data={"title": "다른 작품"},
            ),
        ]
    )
    await db.flush()
    day = date(2026, 10, 15)
    old = datetime(2026, 10, 16, tzinfo=UTC)
    new = old + timedelta(hours=1)
    db.add_all(
        [
            ProductDailyStats(
                product_id=product_id,
                day=day,
                active_users=1,
                succeeded=2,
                messages=4,
                updated_at=old,
            ),
            ProductDailyStats(
                product_id=product_id,
                day=day + timedelta(days=1),
                active_users=1,
                succeeded=3,
                messages=3,
                updated_at=new,
            ),
            ProductDailyStats(
                product_id=other_product,
                day=day,
                active_users=1,
                succeeded=5,
                updated_at=old,
            ),
            ProductVersionDailyStats(
                product_id=product_id,
                product_snapshot_id=version,
                day=day,
                active_users=1,
                succeeded=2,
                messages=4,
                updated_at=old,
            ),
        ]
    )
    # 동일 사용자가 다른 날짜·작품에 있어도 기간 순사용자는 1명이다.
    db.add_all(
        [
            ProductUserDailyActivity(product_id=pid, day=instant, user_id=owner)
            for pid, instant in [
                (product_id, day),
                (product_id, day + timedelta(days=1)),
                (other_product, day),
            ]
        ]
    )
    db.add(
        ProductVersionUserDailyActivity(
            product_id=product_id, product_snapshot_id=version, day=day, user_id=owner
        )
    )
    await db.commit()
    return owner, other, admin, product_id, version, other_version, day


@pytest.mark.asyncio
async def test_real_creator_scope_versions_distinct_and_readonly(db):
    """소유권·버전 소속·기간 DISTINCT와 알려진 버전 0을 DB 읽기 전용으로 검증한다."""
    owner, other, _admin, product, version, other_version, day = await seed_statistics(
        db
    )
    command = CreatorTypes.GetCreatorProductReportCommand(
        product, day, day + timedelta(days=1)
    )
    async with readonly(db):
        result = await CreatorViewsService.get_product_report(
            db, command, actor=CreatorTypes.ActorCommand(owner)
        )
        assert (
            result.totals.active_users == 1
            and result.totals.succeeded == 5
            and result.totals.messages == 7
        )
        assert result.freshness.oldest_updated_at < result.freshness.newest_updated_at
        version_result = await CreatorViewsService.get_product_report(
            db,
            CreatorTypes.GetCreatorProductReportCommand(
                product, day, day + timedelta(days=1), version
            ),
            actor=CreatorTypes.ActorCommand(owner),
        )
        assert (
            version_result.totals.succeeded == 2
            and version_result.days[1].metrics.succeeded == 0
        )
        with pytest.raises(ReportingError, match="not_found"):
            await CreatorViewsService.get_product_report(
                db, command, actor=CreatorTypes.ActorCommand(other)
            )
        with pytest.raises(ReportingError, match="not_found"):
            await CreatorViewsService.get_product_report(
                db,
                CreatorTypes.GetCreatorProductReportCommand(
                    product, day, day, other_version
                ),
                actor=CreatorTypes.ActorCommand(owner),
            )


@pytest.mark.asyncio
async def test_real_operations_global_distinct_queue_and_dirty_coverage(db):
    """전체 기록 합계에서 사용자 중복을 제거하고 대기 작업을 읽기만 한다."""
    (
        owner,
        _other,
        admin,
        product,
        _version,
        _other_version,
        day,
    ) = await seed_statistics(db)
    pending = day + timedelta(days=2)
    db.add(
        ProductStatsDirtyDay(
            product_id=product,
            day=pending,
            requested_at=datetime(2026, 10, 15, tzinfo=UTC),
        )
    )
    await db.commit()
    async with readonly(db):
        actor = OperationsTypes.ActorCommand(admin)
        result = await OperationsViewsService.get_recorded_service_report(
            db,
            OperationsTypes.GetRecordedServiceReportCommand(day, pending),
            actor=actor,
        )
        assert (
            result.recorded_totals.active_users == 1
            and result.recorded_totals.succeeded == 10
        )
        assert (
            result.product_days == 3
            and result.products_with_rows == 2
            and result.pending_product_days == 1
        )
        assert result.coverage == "all_product_day_coverage_not_verified"
        queue = await OperationsViewsService.get_statistics_queue_report(
            db, actor=actor
        )
        assert queue.pending_product_days == 1 and queue.oldest_requested_at is not None
        product_result = await OperationsViewsService.get_product_report(
            db,
            OperationsTypes.GetOperationsProductReportCommand(product, day, pending),
            actor=actor,
        )
        assert (
            product_result.totals is None
            and pending in product_result.freshness.missing_days
        )
        assert pending in product_result.freshness.pending_days
        with pytest.raises(ReportingError, match="forbidden"):
            await OperationsViewsService.get_statistics_queue_report(
                db, actor=OperationsTypes.ActorCommand(owner)
            )
        assert (
            await db.scalar(select(func.count()).select_from(ProductStatsDirtyDay)) == 1
        )


@pytest.mark.asyncio
async def test_real_account_scope_period_end_and_no_autoflush(db):
    """타인·종료 경계의 사실을 제외하고 pending ORM 변경도 조회가 저장하지 않는다."""
    owner, product, release, conversation_id, _character_id = await scenario(db)
    day = date(2026, 10, 15)
    period = get_reporting_period(day, day)
    other = User(id=uuid4(), email=f"{uuid4()}@example.test")
    db.add(other)
    model_id = await db.scalar(select(Model.id).limit(1))
    await db.flush()
    for index, (uid, stamp, status) in enumerate(
        [
            (owner.id, period.start, "succeeded"),
            (owner.id, period.end - timedelta(microseconds=1), "pending"),
            (owner.id, period.end, "failed"),
            (other.id, period.start, "succeeded"),
        ]
    ):
        generation_id = uuid4()
        db.add(
            ProductGeneration(
                id=generation_id,
                user_id=uid,
                conversation_id=conversation_id,
                product_id=product.id,
                product_snapshot_id=release.snapshot_id,
                model_id=model_id,
                model_name="test-model",
                reasoning_effort="low",
                request_key=f"report-{index}",
                input_digest="test",
                status=status,
                created_at=stamp,
                finished_at=stamp if status != "pending" else None,
            )
        )
        await db.flush()
        if status == "succeeded":
            db.add(
                UsageLog(
                    user_id=uid,
                    conversation_id=conversation_id,
                    generation_id=generation_id,
                    product_id=product.id,
                    product_snapshot_id=release.snapshot_id,
                    model_id=model_id,
                    input_tokens=10,
                    output_tokens=4,
                    cost_credit=2,
                    created_at=stamp,
                )
            )
    await db.commit()
    async with readonly(db):
        # 이 미저장 행이 autoflush되면 READ ONLY 트랜잭션에서 즉시 실패한다.
        db.add(ProductStatsDirtyDay(product_id=product.id, day=day))
        result = await AccountViewsService.get_account_report(
            db,
            AccountTypes.GetAccountReportCommand(day, day),
            actor=AccountTypes.ActorCommand(owner.id),
        )
        assert (
            result.generations.succeeded == 1
            and result.generations.pending == 1
            and result.generations.failed == 0
        )
        assert (
            result.usage.usage_records == 1
            and result.usage.input_tokens == 10
            and result.usage.recorded_cost_credit == 2
        )
        for entity in list(db.new):
            db.expunge(entity)


@pytest.mark.asyncio
async def test_real_inactive_owner_and_admin_rejected(db):
    """기존 세션의 캐시가 있어도 최신 사용자 상태·역할로 조회를 거절한다."""
    (
        owner,
        _other,
        admin,
        product,
        _version,
        _other_version,
        day,
    ) = await seed_statistics(db)
    await db.execute(
        text("UPDATE users SET status='suspended' WHERE id=:id"), {"id": owner}
    )
    await db.execute(
        text("UPDATE users SET status='banned' WHERE id=:id"), {"id": admin}
    )
    await db.commit()
    async with readonly(db):
        with pytest.raises(ReportingError, match="forbidden"):
            await CreatorViewsService.get_product_report(
                db,
                CreatorTypes.GetCreatorProductReportCommand(product, day, day),
                actor=CreatorTypes.ActorCommand(owner),
            )
        with pytest.raises(ReportingError, match="forbidden"):
            await OperationsViewsService.get_statistics_queue_report(
                db, actor=OperationsTypes.ActorCommand(admin)
            )
