"""Character-owned storage identities and durable upload/cleanup intents."""

from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class CharacterMedia(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "character_media"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "character_id", "request_id", name="uq_character_media_request"
        ),
        UniqueConstraint(
            "storage_kind", "storage_id", "object_key", name="uq_character_media_object"
        ),
        CheckConstraint(
            "state IN ('pending','ready','deleting','deleted')",
            name="ck_character_media_state",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_character_media_size"),
        CheckConstraint(
            "storage_kind IN ('test_local','s3')", name="ck_character_media_storage"
        ),
    )

    # No cascading FK: retain recovery intents after character/account deletion.
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    character_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    storage_kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_id: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    binding: Mapped[str | None] = mapped_column(Text)
