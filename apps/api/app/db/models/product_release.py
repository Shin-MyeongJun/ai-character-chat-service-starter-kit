from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import UuidPkMixin


class ProductReleaseNote(Base):
    __tablename__ = "product_release_notes"
    __table_args__ = (
        CheckConstraint(
            "change_kind IN ('initial','media','content')", name="ck_release_kind"
        ),
        CheckConstraint(
            "update_policy IN ('automatic','choice')", name="ck_release_policy"
        ),
        CheckConstraint(
            "change_kind = 'media' OR update_policy = 'choice'",
            name="ck_release_content_choice",
        ),
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_snapshots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    change_kind: Mapped[str] = mapped_column(Text, nullable=False)
    update_policy: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductReleaseNoteRevision(UuidPkMixin, Base):
    __tablename__ = "product_release_note_revisions"
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_release_notes.product_snapshot_id", ondelete="CASCADE"),
        nullable=False,
    )
    editor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    previous_summary: Mapped[str] = mapped_column(Text, nullable=False)
    previous_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
