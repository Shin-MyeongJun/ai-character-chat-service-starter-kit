# 통계 일자는 Asia/Seoul 기준이다. DB 조회 범위는 해당 일자의 UTC [시작, 다음 날 시작)으로 변환한다.
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

STATISTICS_ZONE = ZoneInfo("Asia/Seoul")


def statistics_day(instant):
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Statistics require timezone-aware timestamps.")
    return instant.astimezone(STATISTICS_ZONE).date()


def day_bounds(day):
    start = datetime.combine(day, time.min, STATISTICS_ZONE)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)
