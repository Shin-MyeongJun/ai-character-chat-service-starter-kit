from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
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
