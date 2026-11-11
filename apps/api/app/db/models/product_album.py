"""Account discoveries of stable product image items."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProductImageUnlock(Base):
    __tablename__ = "product_image_unlocks"
    __table_args__ = (Index("ix_product_image_unlocks_product_id", "product_id"),)

    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    image_item_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("statement_timestamp()")
    )
