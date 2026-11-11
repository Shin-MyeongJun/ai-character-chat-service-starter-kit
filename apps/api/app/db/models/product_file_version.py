"""Immutable product image files and the references that keep their bytes alive."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    true,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class ProductFileVersion(UuidPkMixin, Base):
    __tablename__ = "product_file_versions"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "product_id", "request_id", name="uq_product_file_request"
        ),
        UniqueConstraint(
            "storage_kind", "storage_id", "object_key", name="uq_product_file_object"
        ),
        CheckConstraint(
            "state IN ('pending','ready','deleting','deleted')",
            name="ck_product_file_state",
        ),
        CheckConstraint(
            "storage_kind IN ('test_local','s3')", name="ck_product_file_storage"
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 33554432", name="ck_product_file_size"
        ),
    )

    # Retain the object identity and request tombstone across product/account deletion.
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_media_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    storage_kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_id: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    awaiting_attachment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    unreferenced_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductFileReference(Base):
    __tablename__ = "product_file_references"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('draft','snapshot','staged_answer','opening','message')",
            name="ck_product_file_reference_kind",
        ),
    )

    file_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_file_versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    reference_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
