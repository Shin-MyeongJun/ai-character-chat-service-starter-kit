from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin
from app.db.models.snapshot._mixins import SnapshotMixin


class ProductSnapshot(SnapshotMixin, UuidPkMixin, Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (
        UniqueConstraint("product_id", "id", name="uq_product_snapshot_identity"),
        UniqueConstraint("product_id", "version", name="uq_product_snapshots_version"),
        CheckConstraint("version > 0", name="ck_product_snapshots_version"),
        CheckConstraint(
            "snapshot_schema_version > 0", name="ck_product_snapshots_schema_version"
        ),
        CheckConstraint(
            "jsonb_typeof(snapshot_data) = 'object'",
            name="ck_product_snapshots_data_object",
        ),
    )

    product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expiry_reason: Mapped[str | None] = mapped_column(Text)


class ProductSnapshotPolicyChange(UuidPkMixin, Base):
    __tablename__ = "product_snapshot_policy_changes"
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    old_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class ProductSnapshotCharacter(UuidPkMixin, Base):
    __tablename__ = "product_snapshot_characters"
    __table_args__ = (
        UniqueConstraint(
            "product_snapshot_id", "id", name="uq_snapshot_character_identity"
        ),
        UniqueConstraint(
            "product_snapshot_id",
            "character_snapshot_id",
            name="uq_product_snapshot_characters_pair",
        ),
        Index("ix_product_snapshot_characters_character", "character_snapshot_id"),
        Index(
            "uq_product_snapshot_characters_primary",
            "product_snapshot_id",
            unique=True,
            postgresql_where=text("is_primary = true"),
        ),
    )

    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    character_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("character_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    role_name: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class ProductSnapshotLorebook(UuidPkMixin, Base):
    __tablename__ = "product_snapshot_lorebooks"
    __table_args__ = (
        UniqueConstraint(
            "product_snapshot_id", "id", name="uq_snapshot_lorebook_identity"
        ),
        CheckConstraint(
            "scope IN ('all','selected')", name="ck_snapshot_lorebook_scope"
        ),
        UniqueConstraint(
            "product_snapshot_id",
            "lorebook_snapshot_id",
            name="uq_product_snapshot_lorebooks_pair",
        ),
        CheckConstraint(
            "role IN ('main', 'detail', 'rule', 'optional')",
            name="ck_product_snapshot_lorebooks_role",
        ),
        Index("ix_product_snapshot_lorebooks_lorebook", "lorebook_snapshot_id"),
    )

    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    lorebook_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lorebook_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="detail")
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="all")


class ProductSnapshotLorebookCharacter(Base):
    __tablename__ = "product_snapshot_lorebook_characters"
    __table_args__ = (
        ForeignKeyConstraint(
            ["product_snapshot_id", "product_character_id"],
            [
                "product_snapshot_characters.product_snapshot_id",
                "product_snapshot_characters.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["product_snapshot_id", "product_lorebook_id"],
            [
                "product_snapshot_lorebooks.product_snapshot_id",
                "product_snapshot_lorebooks.id",
            ],
            ondelete="CASCADE",
        ),
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    product_character_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    product_lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )


class ProductSnapshotStartSet(UuidPkMixin, Base):
    __tablename__ = "product_snapshot_start_sets"
    __table_args__ = (
        UniqueConstraint(
            "product_snapshot_id", "id", name="uq_snapshot_start_identity"
        ),
        UniqueConstraint(
            "product_snapshot_id", "source_entry_id", name="uq_snapshot_start_entry"
        ),
        ForeignKeyConstraint(
            ["product_snapshot_id", "product_lorebook_id"],
            [
                "product_snapshot_lorebooks.product_snapshot_id",
                "product_snapshot_lorebooks.id",
            ],
            ondelete="CASCADE",
        ),
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    product_lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    source_entry_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
