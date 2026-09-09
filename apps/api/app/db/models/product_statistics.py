from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyMetrics:
    active_users: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    succeeded: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    failed: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    cancelled: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    stale: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    messages: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    conversations: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    transitions: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    cost_credit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    # Currency-keyed exact decimal strings: monetary amounts never sum across currencies.
    revenue: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductDailyStats(DailyMetrics, Base):
    __tablename__ = "product_daily_stats"
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class ProductVersionDailyStats(DailyMetrics, Base):
    __tablename__ = "product_version_daily_stats"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class ProductUserDailyActivity(Base):
    __tablename__ = "product_user_daily_activity"
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )


class ProductVersionUserDailyActivity(Base):
    __tablename__ = "product_version_user_daily_activity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )


class ProductStatsDirtyDay(Base):
    __tablename__ = "product_stats_dirty_days"
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
