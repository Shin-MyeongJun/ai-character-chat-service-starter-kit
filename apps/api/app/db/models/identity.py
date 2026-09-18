# 사용자 role/status와 OAuth 연결을 위한 스키마다. 현재 서비스는 관리자 조회만 제공한다.
# 이 테이블 정의만으로 로그인·OAuth·정지 사용자 인증 차단이 연결되는 것은 아니다.
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
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
            "status IN ('active', 'suspended', 'banned')",
            name="ck_users_status",
        ),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=UserRole.USER.value)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=UserStatus.ACTIVE.value,
    )


class UserOAuthAccount(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "user_oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_user_oauth_provider_user"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(Text, nullable=False)
