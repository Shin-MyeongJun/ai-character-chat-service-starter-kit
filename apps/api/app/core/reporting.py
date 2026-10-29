"""영역에 의존하지 않는 날짜·최신성 값과 읽기 입력 검증."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


class ReportingError(Exception):
    """HTTP 표현과 독립적인 조회 실패 코드."""

    def __init__(self, code: str) -> None:
        """조회 실패 종류를 안정적인 코드로 저장한다."""
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PeriodInfo:
    date_from: date
    date_to: date
    start: datetime
    end: datetime
    timezone: str = "Asia/Seoul"


@dataclass(frozen=True, slots=True)
class FreshnessInfo:
    state: str
    oldest_updated_at: datetime | None
    newest_updated_at: datetime | None
    missing_days: tuple[date, ...]
    pending_days: tuple[date, ...]
    method: str


def get_reporting_period(date_from: date, date_to: date) -> PeriodInfo:
    """최대 731일의 포함 날짜 범위를 서울 기준 UTC [start,end)로 변환한다."""
    if (
        type(date_from) is not date
        or type(date_to) is not date
        or date_to < date_from
        or (date_to - date_from).days > 730
        or date_to == date.max
    ):
        raise ReportingError("invalid_period")
    zone = ZoneInfo("Asia/Seoul")
    try:
        start = datetime.combine(date_from, time.min, zone).astimezone(UTC)
        end = datetime.combine(date_to + timedelta(days=1), time.min, zone).astimezone(
            UTC
        )
    except OverflowError as exc:
        raise ReportingError("invalid_period") from exc
    return PeriodInfo(date_from, date_to, start, end)


def validate_reporting_times(start: datetime, end: datetime) -> None:
    """사실 조회의 timezone-aware 비어 있지 않은 최대 731일 범위를 검사한다."""
    if (
        not isinstance(start, datetime)
        or not isinstance(end, datetime)
        or start.utcoffset() is None
        or end.utcoffset() is None
        or not start < end
        or end - start > timedelta(days=731)
    ):
        raise ReportingError("invalid_period")
