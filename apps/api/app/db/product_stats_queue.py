from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.db.models.product_statistics import ProductStatsDirtyDay

STATISTICS_ZONE = ZoneInfo("Asia/Seoul")


def statistics_day(instant):
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Statistics require timezone-aware timestamps.")
    return instant.astimezone(STATISTICS_ZONE).date()


def day_bounds(day):
    start = datetime.combine(day, time.min, STATISTICS_ZONE)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def mark_dirty(session, product_id, instant):
    day = statistics_day(instant)
    statement = insert(ProductStatsDirtyDay).values(product_id=product_id, day=day)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["product_id", "day"], set_={"requested_at": func.now()}
        )
    )
