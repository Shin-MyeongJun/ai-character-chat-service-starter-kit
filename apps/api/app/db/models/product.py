from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class ProductVisibility(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProductLorebookRole(StrEnum):
    MAIN = "main"
    DETAIL = "detail"
    RULE = "rule"
    OPTIONAL = "optional"


class Product(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private', 'public', 'unlisted')",
            name="ck_products_visibility",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name="ck_products_status",
        ),
        Index("ix_products_owner_id", "owner_id"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    opening_message: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=ProductVisibility.PRIVATE.value,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=ProductStatus.DRAFT.value,
    )
    default_model_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("models.id", ondelete="SET NULL"),
    )


class ProductCharacter(UuidPkMixin, Base):
    __tablename__ = "product_characters"
    __table_args__ = (
        UniqueConstraint("product_id", "character_id", name="uq_product_characters_pair"),
        Index("ix_product_characters_product_id", "product_id"),
        Index(
            "uq_product_characters_primary_per_product",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    role_name: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class ProductLorebook(UuidPkMixin, Base):
    __tablename__ = "product_lorebooks"
    __table_args__ = (
        CheckConstraint(
            "role IN ('main', 'detail', 'rule', 'optional')",
            name="ck_product_lorebooks_role",
        ),
        UniqueConstraint("product_id", "lorebook_id", name="uq_product_lorebooks_pair"),
        Index("ix_product_lorebooks_product_id", "product_id"),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lorebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=ProductLorebookRole.DETAIL.value,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
