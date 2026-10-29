# 상품/날짜 집계를 삭제 후 다시 저장한다. 트랜잭션 종료는 상위 호출자 책임이다.
# 작업은 requested_at 순 SKIP LOCKED로 하나를 고른다. 기간 사용자 수는 일별 합이 아니라 DISTINCT다.
from datetime import date, datetime
from typing import TypeAlias
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import (
    Product,
)
from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)
from app.modules.content.product import types as Types

StatisticsReportRow: TypeAlias = tuple[
    list[ProductDailyStats | ProductVersionDailyStats], int, list[date]
]


async def replace_statistics_day(
    session: AsyncSession,
    product_id: UUID,
    day: date,
    build: Types.StatisticsBuildInfo,
    now: datetime,
) -> None:
    metrics, total, users, unique_users = (
        build.metrics,
        build.total,
        build.users,
        build.unique_users,
    )
    for cls in (
        ProductDailyStats,
        ProductVersionDailyStats,
        ProductUserDailyActivity,
        ProductVersionUserDailyActivity,
    ):
        await session.execute(
            delete(cls).where(cls.product_id == product_id, cls.day == day)
        )
    session.add(
        ProductDailyStats(product_id=product_id, day=day, updated_at=now, **total)
    )
    session.add_all(
        ProductVersionDailyStats(
            product_id=product_id,
            product_snapshot_id=sid,
            day=day,
            updated_at=now,
            **metric,
        )
        for sid, metric in metrics.items()
    )
    if users:
        await session.execute(
            insert(ProductVersionUserDailyActivity),
            [
                {
                    "product_id": product_id,
                    "product_snapshot_id": sid,
                    "day": day,
                    "user_id": uid,
                }
                for sid, uid in users
            ],
        )
        await session.execute(
            insert(ProductUserDailyActivity),
            [
                {"product_id": product_id, "day": day, "user_id": uid}
                for uid in unique_users
            ],
        )
    await session.flush()


async def get_pending_statistics_work(
    session: AsyncSession,
) -> ProductStatsDirtyDay | None:
    work: ProductStatsDirtyDay | None = await session.scalar(
        select(ProductStatsDirtyDay)
        .order_by(
            ProductStatsDirtyDay.requested_at,
            ProductStatsDirtyDay.product_id,
            ProductStatsDirtyDay.day,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    return work


async def delete_statistics_work(
    session: AsyncSession, product_id: UUID, day: date
) -> None:
    await session.execute(
        delete(ProductStatsDirtyDay).where(
            ProductStatsDirtyDay.product_id == product_id,
            ProductStatsDirtyDay.day == day,
        )
    )


async def list_published_product_ids(session: AsyncSession) -> list[UUID]:
    return list(
        await session.scalars(
            select(Product.id).where(Product.latest_snapshot_id.is_not(None))
        )
    )


async def get_statistics_report(
    session: AsyncSession,
    product_id: UUID,
    date_from: date,
    date_to: date,
    snapshot_id: UUID | None,
) -> StatisticsReportRow:
    cls = ProductVersionDailyStats if snapshot_id else ProductDailyStats
    activity = (
        ProductVersionUserDailyActivity if snapshot_id else ProductUserDailyActivity
    )
    filters = [cls.product_id == product_id, cls.day >= date_from, cls.day <= date_to]
    activity_filters = [
        activity.product_id == product_id,
        activity.day >= date_from,
        activity.day <= date_to,
    ]
    if snapshot_id:
        filters.append(ProductVersionDailyStats.product_snapshot_id == snapshot_id)
        activity_filters.append(
            ProductVersionUserDailyActivity.product_snapshot_id == snapshot_id
        )
    rows: list[ProductDailyStats | ProductVersionDailyStats] = list(
        await session.scalars(select(cls).where(*filters).order_by(cls.day))
    )
    active_users = await session.scalar(
        select(func.count(func.distinct(activity.user_id))).where(*activity_filters)
    )
    # COUNT DISTINCT without GROUP BY yields one non-null row, even with no activity.
    assert active_users is not None
    pending = list(
        await session.scalars(
            select(ProductStatsDirtyDay.day)
            .where(
                ProductStatsDirtyDay.product_id == product_id,
                ProductStatsDirtyDay.day >= date_from,
                ProductStatsDirtyDay.day <= date_to,
            )
            .order_by(ProductStatsDirtyDay.day)
        )
    )
    return rows, active_users, pending


async def upsert_statistics_work(
    session: AsyncSession, product_id: UUID, day: date
) -> None:
    statement = pg_insert(ProductStatsDirtyDay).values(product_id=product_id, day=day)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["product_id", "day"], set_={"requested_at": func.now()}
        )
    )
