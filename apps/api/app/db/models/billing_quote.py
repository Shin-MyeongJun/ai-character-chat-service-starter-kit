"""Billing-owned insert-only quote snapshots; no balance or reservation state."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class BillingQuote(UuidPkMixin, Base):
    __tablename__ = "billing_quotes"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_key", name="uq_billing_quotes_user_request"
        ),
        CheckConstraint("expires_at > created_at", name="ck_billing_quotes_expiration"),
        CheckConstraint(
            "jsonb_typeof(request_snapshot) = 'object' "
            "AND jsonb_typeof(price_snapshot) = 'object'",
            name="ck_billing_quotes_snapshots",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_key: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    price_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
