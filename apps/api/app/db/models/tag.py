# 태그 사전은 공유하고 공개/내부 여부는 대상별 연결 테이블로 구분한다.
# 정확한 이름만 중복으로 취급하며 정규화 사전·개수 제한·스냅샷은 없다.
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


class InternalTagSource(StrEnum):
    ADMIN = "admin"
    SYSTEM = "system"


class Tag(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_tags_name_not_blank"),
        UniqueConstraint("name", name="uq_tags_name"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class _PublicTagMixin:
    tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    assigned_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class _InternalTagMixin(TimestampMixin):
    tag_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ProductTag(_PublicTagMixin, Base):
    __tablename__ = "product_tags"
    __table_args__ = (Index("ix_product_tags_tag_product", "tag_id", "product_id"),)
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProductInternalTag(_InternalTagMixin, Base):
    __tablename__ = "product_internal_tags"
    __table_args__ = (
        CheckConstraint(
            "source IN ('admin', 'system')", name="ck_product_internal_tags_source"
        ),
        Index("ix_product_internal_tags_tag_product", "tag_id", "product_id"),
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CharacterTag(_PublicTagMixin, Base):
    __tablename__ = "character_tags"
    __table_args__ = (
        Index("ix_character_tags_tag_character", "tag_id", "character_id"),
    )
    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )


class CharacterInternalTag(_InternalTagMixin, Base):
    __tablename__ = "character_internal_tags"
    __table_args__ = (
        CheckConstraint(
            "source IN ('admin', 'system')", name="ck_character_internal_tags_source"
        ),
        Index("ix_character_internal_tags_tag_character", "tag_id", "character_id"),
    )
    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
    )


class LorebookTag(_PublicTagMixin, Base):
    __tablename__ = "lorebook_tags"
    __table_args__ = (Index("ix_lorebook_tags_tag_lorebook", "tag_id", "lorebook_id"),)
    lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lorebooks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class LorebookInternalTag(_InternalTagMixin, Base):
    __tablename__ = "lorebook_internal_tags"
    __table_args__ = (
        CheckConstraint(
            "source IN ('admin', 'system')", name="ck_lorebook_internal_tags_source"
        ),
        Index("ix_lorebook_internal_tags_tag_lorebook", "tag_id", "lorebook_id"),
    )
    lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lorebooks.id", ondelete="CASCADE"),
        primary_key=True,
    )
