# 인증 소유 모델: 최소 식별정보, 자격증명, 일회용 증명과 폐기 가능한 세션을 저장한다.
# 토큰 평문은 저장하지 않는다. Outbox의 재전송용 토큰은 암호화해 단기 보관한다.
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"


class User(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        CheckConstraint(
            "email = lower(btrim(email))", name="ck_users_email_normalized"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'banned')",
            name="ck_users_status",
        ),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    pending_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=UserRole.USER.value
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=UserStatus.ACTIVE.value,
    )


class UserOAuthAccount(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "user_oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_user_id", name="uq_user_oauth_provider_user"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)


class AuthSession(UuidPkMixin, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    refresh_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthActionToken(UuidPkMixin, Base):
    __tablename__ = "auth_action_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify', 'reset')", name="ck_auth_action_purpose"
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthMailOutbox(UuidPkMixin, Base):
    __tablename__ = "auth_mail_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'cancelled', 'failed')",
            name="ck_auth_mail_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_auth_mail_attempt_count"),
        CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (status <> 'processing' AND claim_token IS NULL AND lease_until IS NULL)",
            name="ck_auth_mail_claim",
        ),
        CheckConstraint(
            "(status IN ('pending', 'processing') AND encrypted_token IS NOT NULL) "
            "OR (status IN ('sent', 'cancelled', 'failed') AND encrypted_token IS NULL)",
            name="ck_auth_mail_payload",
        ),
        Index("ix_auth_mail_due", "status", "available_at", "id"),
        Index("ix_auth_mail_lease", "status", "lease_until", "id"),
    )
    token_hash: Mapped[str] = mapped_column(
        Text,
        ForeignKey("auth_action_tokens.token_hash", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    encrypted_token: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class AuthOAuthAttempt(Base):
    __tablename__ = "auth_oauth_attempts"
    state_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    # IP·이메일의 HMAC와 시간 버킷만 보관하여 평문 식별자 축적을 피한다.
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
