# 편집 캐릭터와 감정 이미지·범용 자산이다. 캐릭터별 감정 태그는 유일하며 기본 이미지는 최대 하나다.
# media_id=None은 관리 저장소에 등록되지 않은 기존 URL 데이터다.
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class CharacterVisibility(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


class CharacterStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class CharacterAssetType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"


class Character(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private', 'public', 'unlisted')",
            name="ck_characters_visibility",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name="ck_characters_status",
        ),
        Index("ix_characters_owner_id", "owner_id"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    persona_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=CharacterVisibility.PRIVATE.value,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=CharacterStatus.DRAFT.value,
    )
    default_model_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="SET NULL"),
    )


class CharacterImage(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "character_images"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "emotion_tag", name="uq_character_images_emotion"
        ),
        Index(
            "uq_character_images_default_per_character",
            "character_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    emotion_tag: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("character_media.id", ondelete="RESTRICT"),
        index=True,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class CharacterAsset(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "character_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('image', 'audio', 'video')",
            name="ck_character_assets_asset_type",
        ),
        Index("ix_character_assets_character_id", "character_id"),
    )

    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    media_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("character_media.id", ondelete="RESTRICT"),
        index=True,
    )
