# version은 원본별 발행 순번, snapshot_schema_version은 JSON 구조 버전이다.
# 새 행 발행으로 내용을 보존하지만 ORM 선언 자체에 payload UPDATE를 막는 장치는 없다.
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class SnapshotMixin:
    """Publication data: write a new snapshot instead of updating its payload."""

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    snapshot_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
