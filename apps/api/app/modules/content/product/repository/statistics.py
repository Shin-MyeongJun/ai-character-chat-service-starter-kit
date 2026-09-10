from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

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


async def replace_statistics_day(session, product_id, day, build, now) -> None:
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


async def get_pending_statistics_work(session):
    return await session.scalar(
        select(ProductStatsDirtyDay)
        .order_by(
            ProductStatsDirtyDay.requested_at,
            ProductStatsDirtyDay.product_id,
            ProductStatsDirtyDay.day,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )


async def delete_statistics_work(session, product_id, day) -> None:
    await session.execute(
        delete(ProductStatsDirtyDay).where(
            ProductStatsDirtyDay.product_id == product_id,
            ProductStatsDirtyDay.day == day,
        )
    )


async def list_published_product_ids(session):
    return list(
        await session.scalars(
            select(Product.id).where(Product.latest_snapshot_id.is_not(None))
        )
    )


async def get_statistics_report(session, product_id, date_from, date_to, snapshot_id):
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
        filters.append(cls.product_snapshot_id == snapshot_id)
        activity_filters.append(activity.product_snapshot_id == snapshot_id)
    rows = list(await session.scalars(select(cls).where(*filters).order_by(cls.day)))
    active_users = await session.scalar(
        select(func.count(func.distinct(activity.user_id))).where(*activity_filters)
    )
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


async def upsert_statistics_work(session, product_id, day):
    statement = pg_insert(ProductStatsDirtyDay).values(product_id=product_id, day=day)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["product_id", "day"], set_={"requested_at": func.now()}
        )
    )
