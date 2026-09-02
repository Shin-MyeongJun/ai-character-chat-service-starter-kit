from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class ConversationMemoryType(StrEnum):
    SUMMARY = "summary"
    FACT = "fact"
    EVENT = "event"


class ConversationMemory(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "conversation_memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('summary', 'fact', 'event')",
            name="ck_conversation_memories_memory_type",
        ),
        Index("ix_conversation_memories_conversation_id", "conversation_id"),
        Index(
            "ix_conversation_memories_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 100},
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    source_message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
    )
