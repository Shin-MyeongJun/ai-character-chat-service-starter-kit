"""Currency wallets and immutable, unclassified legacy credit history."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class CreditTransactionReason(StrEnum):
    CHAT_USAGE = "chat_usage"
    PURCHASE = "purchase"
    REFUND = "refund"
    SUBSCRIPTION_GRANT = "subscription_grant"
    GRANT = "grant"
    CONSUME = "consume"


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_credit_accounts_balance_non_negative"),
        CheckConstraint(
            "reserved_credit >= 0 AND reserved_credit <= balance",
            name="ck_credit_accounts_reserved_credit",
        ),
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
    reserved_credit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
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
        ForeignKeyConstraint(
            ["user_id", "currency_code"],
            ["credit_wallets.user_id", "credit_wallets.currency_code"],
            name="fk_credit_transactions_wallet",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_credit_transactions_history",
            "user_id",
            "currency_code",
            "created_at",
            "id",
        ),
        UniqueConstraint(
            "id",
            "user_id",
            "currency_code",
            name="uq_credit_transactions_currency_identity",
        ),
        UniqueConstraint(
            "user_id",
            "currency_code",
            "namespace",
            "operation",
            "request_key",
            name="uq_credit_transactions_operation",
        ),
        CheckConstraint(
            "(operation = 'legacy' AND currency_code IS NULL AND namespace IS "
            "NULL AND request_key IS NULL) OR (operation IN ('grant', "
            "'consume') AND currency_code IS NOT NULL AND namespace IS NOT "
            "NULL AND request_key IS NOT NULL)",
            name="ck_credit_transactions_operation",
        ),
        # A retried movement can insert only once.
        # The UNIQUE constraint turns duplicate credit debit attempts into a DB error.
        Index(
            "uq_credit_transactions_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("operation = 'legacy'"),
        ),
        UniqueConstraint(
            "user_id",
            "currency_code",
            "namespace",
            "operation",
            "idempotency_key",
            name="uq_credit_transactions_scoped_key",
        ),
        CheckConstraint(
            "operation = 'legacy' OR (operation = 'grant' AND amount > 0) OR "
            "(operation = 'consume' AND amount <= 0)",
            name="ck_credit_transactions_sign",
        ),
        Index("ix_credit_transactions_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    currency_code: Mapped[str | None] = mapped_column(Text)
    namespace: Mapped[str | None] = mapped_column(Text)
    request_key: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    operation: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'legacy'")
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


class CreditReservation(UuidPkMixin, Base):
    __tablename__ = "credit_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["transaction_id", "user_id", "currency_code"],
            [
                "credit_transactions.id",
                "credit_transactions.user_id",
                "credit_transactions.currency_code",
            ],
            name="fk_credit_reservations_transaction_currency",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_credit_reservations_history",
            "user_id",
            "currency_code",
            "created_at",
            "id",
        ),
        UniqueConstraint(
            "user_id",
            "currency_code",
            "namespace",
            "request_key",
            name="uq_credit_reservations_user_request",
        ),
        UniqueConstraint(
            "user_id",
            "currency_code",
            "namespace",
            "settlement_key",
            name="uq_credit_reservations_settlement",
        ),
        Index(
            "uq_credit_reservations_legacy_request",
            "user_id",
            "namespace",
            "request_key",
            unique=True,
            postgresql_where=text("currency_code IS NULL"),
        ),
        Index(
            "uq_credit_reservations_legacy_settlement",
            "settlement_key",
            unique=True,
            postgresql_where=text("currency_code IS NULL"),
        ),
        UniqueConstraint(
            "id", "user_id", "request_key", name="uq_credit_reservations_identity"
        ),
        UniqueConstraint("transaction_id", name="uq_credit_reservations_transaction"),
        ForeignKeyConstraint(
            ["user_id", "currency_code"],
            ["credit_wallets.user_id", "credit_wallets.currency_code"],
            name="fk_credit_reservations_wallet",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(allocation_status = 'legacy_unknown' AND currency_code IS NULL "
            "AND free_amount IS NULL AND paid_amount IS NULL) OR "
            "(allocation_status = 'allocated' AND currency_code IS NOT NULL "
            "AND free_amount IS NOT NULL AND paid_amount IS NOT NULL AND "
            "free_amount >= 0 AND paid_amount >= 0 AND free_amount::numeric + "
            "paid_amount::numeric = reserved_credit)",
            name="ck_credit_reservations_allocation",
        ),
        CheckConstraint("reserved_credit >= 0", name="ck_credit_reservations_amount"),
        CheckConstraint(
            "(status = 'reserved' AND result_id IS NULL "
            "AND transaction_id IS NULL AND finalized_at IS NULL) OR "
            "(status = 'committed' AND result_id IS NOT NULL "
            "AND transaction_id IS NOT NULL AND finalized_at IS NOT NULL) OR "
            "(status = 'released' AND result_id IS NULL "
            "AND transaction_id IS NULL AND finalized_at IS NOT NULL)",
            name="ck_credit_reservations_state",
        ),
        Index("ix_credit_reservations_user_status", "user_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", name="fk_credit_reservations_user", ondelete="RESTRICT"),
        nullable=False,
    )
    currency_code: Mapped[str | None] = mapped_column(Text)
    free_amount: Mapped[int | None] = mapped_column(BigInteger)
    paid_amount: Mapped[int | None] = mapped_column(BigInteger)
    allocation_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'legacy_unknown'")
    )
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    namespace: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    settlement_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    reserved_credit: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("credit_transactions.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditWallet(Base):
    __tablename__ = "credit_wallets"
    __table_args__ = (
        CheckConstraint(
            "currency_code ~ '^[A-Z][A-Z0-9_]{0,31}$'",
            name="ck_credit_wallets_currency",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    currency_code: Mapped[str] = mapped_column(Text, primary_key=True)


class CreditBalance(Base):
    __tablename__ = "credit_balances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "currency_code"],
            ["credit_wallets.user_id", "credit_wallets.currency_code"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("bucket IN ('free', 'paid')", name="ck_credit_balances_bucket"),
        CheckConstraint(
            "balance >= 0 AND reserved_credit >= 0 AND reserved_credit <= balance",
            name="ck_credit_balances_amount",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    currency_code: Mapped[str] = mapped_column(Text, primary_key=True)
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    balance: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    reserved_credit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )


class CreditTransactionEntry(Base):
    __tablename__ = "credit_transaction_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["transaction_id", "user_id", "currency_code"],
            [
                "credit_transactions.id",
                "credit_transactions.user_id",
                "credit_transactions.currency_code",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["user_id", "currency_code", "bucket"],
            [
                "credit_balances.user_id",
                "credit_balances.currency_code",
                "credit_balances.bucket",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount <> 0", name="ck_credit_transaction_entries_amount"),
    )
    transaction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    bucket: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    currency_code: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
