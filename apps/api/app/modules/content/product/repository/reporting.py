"""Product가 소유한 기존 통계의 읽기 전용 조회. 집계·큐 상태를 변경하지 않는다."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TypeAlias
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product_statistics import (
    ProductDailyStats,
    ProductStatsDirtyDay,
    ProductUserDailyActivity,
    ProductVersionDailyStats,
    ProductVersionUserDailyActivity,
)

COUNTERS = (
    "succeeded",
    "failed",
    "cancelled",
    "stale",
    "messages",
    "conversations",
    "transitions",
    "input_tokens",
    "output_tokens",
    "cost_credit",
)

# COUNT/COUNT DISTINCT, MIN/MAX timestamp, then the ten COUNTERS sums.
# PostgreSQL SUM(bigint) may return Decimal; the mapper keeps the existing int conversion.
ServiceReportingMetricsRow: TypeAlias = tuple[
    int,
    int,
    datetime | None,
    datetime | None,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
    int | Decimal,
]
StatisticsQueueRow: TypeAlias = tuple[int, datetime | None]


@dataclass
class ProductReportingRow:
    rows: list[ProductDailyStats] | list[ProductVersionDailyStats]
    root_rows: list[ProductDailyStats]
    active_users: int
    pending_days: list[date]


@dataclass
class ServiceReportingRow:
    metrics: ServiceReportingMetricsRow
    active_users: int
    pending: StatisticsQueueRow


async def get_product_reporting_statistics(
    session: AsyncSession,
    product_id: UUID,
    date_from: date,
    date_to: date,
    snapshot_id: UUID | None,
) -> ProductReportingRow:
    """작품/버전 집계와 부모 일별 집계·중복 제거 사용자·dirty 날짜를 조회한다."""
    root = ProductDailyStats
    roots = list(
        (
            await session.scalars(
                select(root)
                .where(
                    root.product_id == product_id,
                    root.day >= date_from,
                    root.day <= date_to,
                )
                .order_by(root.day)
            )
        ).all()
    )
    rows: list[ProductDailyStats] | list[ProductVersionDailyStats]
    activity: type[ProductUserDailyActivity] | type[ProductVersionUserDailyActivity]
    if snapshot_id is None:
        # This branch keeps the same rows/root_rows list object, as before.
        rows = roots
        activity = ProductUserDailyActivity
        filters = [
            activity.product_id == product_id,
            activity.day >= date_from,
            activity.day <= date_to,
        ]
    else:
        model = ProductVersionDailyStats
        rows = list(
            (
                await session.scalars(
                    select(model)
                    .where(
                        model.product_id == product_id,
                        model.product_snapshot_id == snapshot_id,
                        model.day >= date_from,
                        model.day <= date_to,
                    )
                    .order_by(model.day)
                )
            ).all()
        )
        activity = ProductVersionUserDailyActivity
        filters = [
            activity.product_id == product_id,
            ProductVersionUserDailyActivity.product_snapshot_id == snapshot_id,
            activity.day >= date_from,
            activity.day <= date_to,
        ]
    active_users = await session.scalar(
        select(func.count(func.distinct(activity.user_id))).where(*filters)
    )
    # Ungrouped COUNT DISTINCT returns a non-null row even for empty activity.
    assert active_users is not None
    queue = ProductStatsDirtyDay
    pending = list(
        (
            await session.scalars(
                select(queue.day)
                .where(
                    queue.product_id == product_id,
                    queue.day >= date_from,
                    queue.day <= date_to,
                )
                .order_by(queue.day)
            )
        ).all()
    )
    return ProductReportingRow(rows, roots, active_users, pending)


async def get_service_reporting_statistics(
    session: AsyncSession, date_from: date, date_to: date
) -> ServiceReportingRow:
    """기록된 작품 집계만 합산하고 기간·작품 간 활성 사용자를 DISTINCT로 센다."""
    model = ProductDailyStats
    # Result.tuples() preserves runtime Rows and types positions on SQLAlchemy >= 2.0.
    metrics: ServiceReportingMetricsRow = (
        (
            await session.execute(
                select(
                    func.count(),
                    func.count(func.distinct(model.product_id)),
                    func.min(model.updated_at),
                    func.max(model.updated_at),
                    *(
                        func.coalesce(func.sum(getattr(model, field)), 0)
                        for field in COUNTERS
                    ),
                ).where(model.day >= date_from, model.day <= date_to)
            )
        )
        .tuples()
        .one()
    )
    activity = ProductUserDailyActivity
    users = await session.scalar(
        select(func.count(func.distinct(activity.user_id))).where(
            activity.day >= date_from, activity.day <= date_to
        )
    )
    assert users is not None
    queue = ProductStatsDirtyDay
    pending: StatisticsQueueRow = (
        (
            await session.execute(
                select(func.count(), func.min(queue.requested_at)).where(
                    queue.day >= date_from, queue.day <= date_to
                )
            )
        )
        .tuples()
        .one()
    )
    return ServiceReportingRow(metrics, users, pending)


async def get_statistics_queue(session: AsyncSession) -> StatisticsQueueRow:
    """전체 재집계 대기 작품-날짜 개수와 가장 오래된 최신 요청 시각을 조회한다."""
    queue = ProductStatsDirtyDay
    row: StatisticsQueueRow = (
        (await session.execute(select(func.count(), func.min(queue.requested_at))))
        .tuples()
        .one()
    )
    return row
