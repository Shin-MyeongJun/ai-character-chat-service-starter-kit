# 신고·감사 기록을 위한 기존 스키마다. 현재 governance 서비스의 상태 변경이 이 행들을 자동 생성하지는 않는다.
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class ModerationTargetType(StrEnum):
    CHARACTER = "character"
    MESSAGE = "message"


class ModerationFlagStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class ModerationFlag(UuidPkMixin, Base):
    __tablename__ = "moderation_flags"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('character', 'message')",
            name="ck_moderation_flags_target_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'reviewed', 'dismissed')",
            name="ck_moderation_flags_status",
        ),
        Index("ix_moderation_flags_status_created_at", "status", "created_at"),
        Index("ix_moderation_flags_target", "target_type", "target_id"),
    )

    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    flagged_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UuidPkMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_admin_id_created_at", "admin_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
    )

    admin_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
