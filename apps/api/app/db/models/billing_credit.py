"""Billing owns only the quote-to-reservation binding."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.credit import CreditReservation as CreditReservation


class BillingCreditBinding(Base):
    __tablename__ = "billing_credit_bindings"
    __table_args__ = (
        UniqueConstraint("quote_id", name="uq_billing_credit_bindings_quote"),
        UniqueConstraint(
            "user_id", "request_key", name="uq_billing_credit_bindings_user_request"
        ),
        ForeignKeyConstraint(
            ["reservation_id", "user_id", "request_key"],
            [
                "credit_reservations.id",
                "credit_reservations.user_id",
                "credit_reservations.request_key",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["quote_id", "user_id", "request_key"],
            [
                "billing_quotes.id",
                "billing_quotes.user_id",
                "billing_quotes.request_key",
            ],
            ondelete="RESTRICT",
        ),
    )
    reservation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    quote_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
