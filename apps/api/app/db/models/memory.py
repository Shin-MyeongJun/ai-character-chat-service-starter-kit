# 요약 원문 범위·대화 revision·프롬프트 버전과 임베딩 모델을 보존한다. DB 벡터는 1536차원이다.
# index_status=ready는 검색 준비 상태이며 기존 벡터와 새 모델이 호환된다는 뜻은 아니다.
# MemoryJob의 generation은 LLM 생성 ID가 아니라 예약 요청 세대다. scope_generation은 claim 시점 세대다.
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
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
        CheckConstraint(
            "(embedding_provider IS NULL) = (embedding_model IS NULL)",
            name="ck_conversation_memories_embedding_identity",
        ),
        CheckConstraint(
            "index_status IN ('pending', 'ready', 'failed')",
            name="ck_conversation_memories_index_status",
        ),
        CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_conversation_memories_importance",
        ),
        CheckConstraint(
            "source_start_position IS NULL OR source_end_position >= source_start_position",
            name="ck_conversation_memories_source_range",
        ),
        CheckConstraint(
            "index_status <> 'ready' OR (embedding IS NOT NULL AND embedding_provider IS NOT NULL AND embedding_model IS NOT NULL AND embedding_dimension IS NOT NULL)",
            name="ck_conversation_memories_ready_embedding",
        ),
        UniqueConstraint(
            "conversation_id",
            "memory_type",
            "source_start_position",
            "source_end_position",
            "conversation_revision",
            "prompt_version",
            name="uq_conversation_memory_summary_source",
        ),
        Index("ix_conversation_memories_conversation_id", "conversation_id"),
        Index(
            "ix_conversation_memories_embedding_identity",
            "embedding_provider",
            "embedding_model",
        ),
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
    embedding_provider: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_settings: Mapped[dict | None] = mapped_column(JSON)
    embedded_content_digest: Mapped[str | None] = mapped_column(Text)
    index_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    importance: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.5")
    )
    summary_provider: Mapped[str | None] = mapped_column(Text)
    summary_model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    source_start_position: Mapped[int | None] = mapped_column(BigInteger)
    source_end_position: Mapped[int | None] = mapped_column(BigInteger)
    source_digest: Mapped[str | None] = mapped_column(Text)
    conversation_revision: Mapped[int | None] = mapped_column(Integer)
    summary_input_tokens: Mapped[int | None] = mapped_column(Integer)
    summary_output_tokens: Mapped[int | None] = mapped_column(Integer)
    embedding_tokens: Mapped[int | None] = mapped_column(Integer)
    source_message_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL")
    )


class MemoryJob(TimestampMixin, Base):
    __tablename__ = "memory_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'idle', 'failed')",
            name="ck_memory_jobs_status",
        ),
        CheckConstraint(
            "requested_generation >= completed_generation",
            name="ck_memory_jobs_generation",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_memory_jobs_attempt_count"),
        Index("ix_memory_jobs_claim", "status", "next_attempt_at", "updated_at"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    completed_generation: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    scope_generation: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    lease_owner: Mapped[str | None] = mapped_column(Text)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error_kind: Mapped[str | None] = mapped_column(Text)
