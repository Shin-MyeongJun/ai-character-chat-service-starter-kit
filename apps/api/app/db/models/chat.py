from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
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
        ForeignKeyConstraint(
            ["product_id", "product_snapshot_id"],
            ["product_snapshots.product_id", "product_snapshots.id"],
        ),
        ForeignKeyConstraint(
            ["initial_snapshot_id", "start_set_id"],
            [
                "product_snapshot_start_sets.product_snapshot_id",
                "product_snapshot_start_sets.id",
            ],
        ),
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
    is_group: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    active_model_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="SET NULL"),
    )
    product_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    start_set_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    initial_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id")
    )


class ConversationCharacter(UuidPkMixin, Base):
    __tablename__ = "conversation_characters"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "product_character_id",
            name="uq_conversation_snapshot_character",
        ),
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
    character_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="SET NULL"),
    )
    product_character_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshot_characters.id")
    )
    role_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Message(UuidPkMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_message_position"),
        ForeignKeyConstraint(
            ["generation_id", "product_snapshot_id"],
            ["product_generations.id", "product_generations.product_snapshot_id"],
        ),
        ForeignKeyConstraint(
            ["product_snapshot_id", "product_character_id"],
            [
                "product_snapshot_characters.product_snapshot_id",
                "product_snapshot_characters.id",
            ],
        ),
        CheckConstraint(
            "sender_type IN ('user', 'character', 'system')",
            name="ck_messages_sender_type",
        ),
        CheckConstraint(
            "product_snapshot_id IS NULL OR sender_type <> 'character' OR product_character_id IS NOT NULL",
            name="ck_messages_character_sender_has_character",
        ),
        Index(
            "ix_messages_conversation_id_created_at", "conversation_id", "created_at"
        ),
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
    position: Mapped[int] = mapped_column(BigInteger, Identity(), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    generation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    product_snapshot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id")
    )
    product_character_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
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


class ConversationVersionChange(UuidPkMixin, Base):
    __tablename__ = "conversation_version_changes"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "to_snapshot_id", name="uq_conversation_version_change"
        ),
        CheckConstraint(
            "mode IN ('automatic','choice')", name="ck_conversation_version_change_mode"
        ),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False
    )
    to_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MessageRequest(Base):
    """Persistent retry receipt, including after the resulting message is deleted."""

    __tablename__ = "chat_message_requests"
    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    request_key: Mapped[str] = mapped_column(Text, primary_key=True)
    input_digest: Mapped[str] = mapped_column(Text, nullable=False)
    message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )
