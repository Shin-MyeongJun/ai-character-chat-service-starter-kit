from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class SenderType(StrEnum):
    USER = "user"
    CHARACTER = "character"
    SYSTEM = "system"


class Conversation(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_id_created_at", "user_id", "created_at"),
        Index("ix_conversations_product_id_created_at", "product_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(Text)
    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    active_model_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="SET NULL"),
    )


class ConversationCharacter(UuidPkMixin, Base):
    __tablename__ = "conversation_characters"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "character_id",
            name="uq_conversation_characters_pair",
        ),
        Index("ix_conversation_characters_conversation_id", "conversation_id"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Message(UuidPkMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('user', 'character', 'system')",
            name="ck_messages_sender_type",
        ),
        CheckConstraint(
            "(sender_type <> 'character') OR (character_id IS NOT NULL)",
            name="ck_messages_character_sender_has_character",
        ),
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
        Index("ix_messages_model_id_created_at", "model_id", "created_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_type: Mapped[str] = mapped_column(Text, nullable=False)
    character_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="SET NULL"),
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    emotion_tag: Mapped[str | None] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    model_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="SET NULL"),
    )
    generated_by_ai: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
