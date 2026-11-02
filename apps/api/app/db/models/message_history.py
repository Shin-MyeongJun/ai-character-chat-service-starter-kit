"""Chat-owned change stamps; PostgreSQL message triggers maintain the version."""

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatHistoryVersion(Base):
    __tablename__ = "chat_history_versions"
    __table_args__ = (CheckConstraint("version >= 0", name="ck_chat_history_version"),)

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
