"""Billing reservation lifecycle; settled movements use credit_transactions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class CreditReservation(UuidPkMixin, Base):
    __tablename__ = "credit_reservations"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_key", name="uq_credit_reservations_user_request"
        ),
        UniqueConstraint("quote_id", name="uq_credit_reservations_quote"),
        UniqueConstraint("transaction_id", name="uq_credit_reservations_transaction"),
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
        ForeignKey("credit_accounts.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quote_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("billing_quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
