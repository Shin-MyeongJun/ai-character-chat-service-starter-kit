# 사용량·결제·구독·크레딧 스키마다. 현재 billing은 usage와 상품 귀속을 기록하고 credit 서비스는 비어 있다.
# 금액은 Decimal 통화 값, 크레딧은 정수다. usage의 nullable 참조는 이전 데이터와 삭제된 대화를 허용한다.
# generation별 사용량 UNIQUE는 중복 행을 막으며 잔액 차감까지 보장하지 않는다.
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class CreditTransactionReason(StrEnum):
    CHAT_USAGE = "chat_usage"
    PURCHASE = "purchase"
    REFUND = "refund"
    SUBSCRIPTION_GRANT = "subscription_grant"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_credit_accounts_balance_non_negative"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CreditTransaction(UuidPkMixin, Base):
    __tablename__ = "credit_transactions"
    __table_args__ = (
        CheckConstraint(
            "reason IN ('chat_usage', 'purchase', 'refund', 'subscription_grant')",
            name="ck_credit_transactions_reason",
        ),
        # Same chat request retried with the same key can insert only once.
        # The UNIQUE constraint turns duplicate credit debit attempts into a DB error.
        UniqueConstraint(
            "idempotency_key", name="uq_credit_transactions_idempotency_key"
        ),
        Index("ix_credit_transactions_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class UsageLog(UuidPkMixin, Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        UniqueConstraint("generation_id", name="uq_usage_generation"),
        ForeignKeyConstraint(
            ["generation_id", "product_snapshot_id"],
            ["product_generations.id", "product_generations.product_snapshot_id"],
        ),
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cost_credit >= 0",
            name="ck_usage_nonnegative",
        ),
        Index("ix_usage_logs_user_id_created_at", "user_id", "created_at"),
        Index(
            "ix_usage_logs_conversation_id_created_at", "conversation_id", "created_at"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
    )
    model_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    product_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    product_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reasoning_effort: Mapped[str | None] = mapped_column(Text)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_credit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class SubscriptionPlan(UuidPkMixin, Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly')",
            name="ck_subscription_plans_billing_cycle",
        ),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    monthly_credit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    billing_cycle: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class UserSubscription(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'canceled', 'expired', 'past_due')",
            name="ck_user_subscriptions_status",
        ),
        Index("ix_user_subscriptions_user_id_status", "user_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class Payment(UuidPkMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        UniqueConstraint("pg_transaction_id", name="uq_payments_pg_transaction_id"),
        Index("ix_payments_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, server_default="KRW")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    pg_provider: Mapped[str] = mapped_column(Text, nullable=False)
    pg_transaction_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
