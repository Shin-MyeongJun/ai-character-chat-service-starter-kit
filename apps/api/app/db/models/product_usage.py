# 생성 상태·재요청 키·외부 결과 staging과 확정 결제 귀속을 저장한다. 실제 차감 구현은 없다.
# request_key는 사용자 전체 범위에서 유일하다. answer_lease_until=None인 기존 생성은 답변 복구 대상에서 제외된다.
# history_invalidated_at은 원문 변경 표시이며 기록된 사용량 삭제를 뜻하지 않는다.
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.json_types import JsonObject
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
        CheckConstraint(
            "answer_recovery_attempts >= 0", name="ck_answer_recovery_attempts"
        ),
        Index("ix_generation_product_finished", "product_id", "finished_at"),
        Index("ix_generation_created_id", "created_at", "id"),
        Index("ix_generation_conversation_created", "conversation_id", "created_at"),
        Index(
            "ix_generation_pending_answer_lease",
            "answer_lease_until",
            postgresql_where=text(
                "status = 'pending' AND answer_lease_until IS NOT NULL"
            ),
        ),
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
    answer_metadata: Mapped[JsonObject | None] = mapped_column(JSONB)
    answer_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answer_recovery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    answer_recovery_next_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    answer_recovery_quarantined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class AnswerRecoveryAttempt(Base):
    """Committed before finalization; an interrupted attempt still consumes budget."""

    __tablename__ = "answer_recovery_attempts"
    __table_args__ = (
        CheckConstraint("attempt_count > 0", name="ck_recovery_attempt_number"),
        CheckConstraint(
            "(operator IS NULL AND reason IS NULL) OR "
            "(operator IS NOT NULL AND reason IS NOT NULL AND "
            "length(trim(operator)) BETWEEN 1 AND 120 AND length(trim(reason)) BETWEEN 1 AND 1000)",
            name="ck_recovery_operator_reason",
        ),
    )
    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_generations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    operator: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    failure_class: Mapped[str | None] = mapped_column(Text)


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
