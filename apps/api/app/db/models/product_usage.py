"""Execution and payment attribution facts; monetary debits remain in billing."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class ProductGeneration(UuidPkMixin, Base):
    __tablename__ = "product_generations"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_generation_request"),
        UniqueConstraint("id", "product_snapshot_id", name="uq_generation_version"),
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
        CheckConstraint(
            "status IN ('pending','succeeded','failed','cancelled','stale')",
            name="ck_generation_status",
        ),
        CheckConstraint("message_count >= 0", name="ck_generation_messages"),
        Index("ix_generation_product_finished", "product_id", "finished_at"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    model_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("models.id"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    result_digest: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history_invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    answer_metadata: Mapped[dict | None] = mapped_column(JSONB)
    answer_lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class ProductPaymentEvent(UuidPkMixin, Base):
    __tablename__ = "product_payment_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_product_payment_event_key"),
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
        CheckConstraint("kind IN ('sale','refund')", name="ck_product_payment_kind"),
        CheckConstraint(
            "(kind='sale' AND sale_id IS NULL) OR (kind='refund' AND sale_id IS NOT NULL)",
            name="ck_product_payment_parent",
        ),
        CheckConstraint("amount > 0", name="ck_product_payment_amount"),
        Index("ix_product_payment_period", "product_id", "attributed_at"),
    )
    payment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payments.id"), nullable=False
    )
    sale_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_payment_events.id")
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("products.id"), nullable=False
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attributed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
