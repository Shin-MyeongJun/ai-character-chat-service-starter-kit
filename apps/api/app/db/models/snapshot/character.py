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
from app.db.models._mixins import UuidPkMixin
from app.db.models.snapshot._mixins import SnapshotMixin


class CharacterSnapshot(SnapshotMixin, UuidPkMixin, Base):
    __tablename__ = "character_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "character_id", "version", name="uq_character_snapshots_version"
        ),
        CheckConstraint("version > 0", name="ck_character_snapshots_version"),
        CheckConstraint(
            "snapshot_schema_version > 0", name="ck_character_snapshots_schema_version"
        ),
        CheckConstraint(
            "jsonb_typeof(snapshot_data) = 'object'",
            name="ck_character_snapshots_data_object",
        ),
    )

    character_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("characters.id", ondelete="SET NULL"),
    )


class CharacterSnapshotImage(UuidPkMixin, Base):
    __tablename__ = "character_snapshot_images"
    __table_args__ = (
        UniqueConstraint(
            "character_snapshot_id", "emotion_tag", name="uq_snapshot_image_emotion"
        ),
        Index(
            "uq_snapshot_image_default",
            "character_snapshot_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )
    character_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("character_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_image_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    emotion_tag: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CharacterSnapshotAsset(UuidPkMixin, Base):
    __tablename__ = "character_snapshot_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('image','audio','video')", name="ck_snapshot_asset_type"
        ),
        Index("ix_snapshot_assets_parent", "character_snapshot_id"),
    )
    character_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("character_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
