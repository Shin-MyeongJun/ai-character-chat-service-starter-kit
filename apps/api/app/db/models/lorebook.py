from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class LorebookVisibility(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"
    UNLISTED = "unlisted"


class LorebookStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class LorebookEntryType(StrEnum):
    AUTHOR_NOTE = "author_note"
    WORLD = "world"
    GENRE = "genre"
    RULE = "rule"
    LOCATION = "location"
    FACTION = "faction"
    CHARACTER_RELATION = "character_relation"
    EVENT = "event"
    TERM = "term"
    SECRET = "secret"


class LorebookEntryActivationType(StrEnum):
    ALWAYS = "always"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    MANUAL = "manual"


class LorebookEntryMatchMode(StrEnum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"


class LorebookEntryPlacement(StrEnum):
    SYSTEM_TOP = "system_top"
    BEFORE_MEMORY = "before_memory"
    AFTER_MEMORY = "after_memory"
    BEFORE_HISTORY = "before_history"
    NEAR_USER_MESSAGE = "near_user_message"


class Lorebook(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "lorebooks"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private', 'public', 'unlisted')",
            name="ck_lorebooks_visibility",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name="ck_lorebooks_status",
        ),
        Index("ix_lorebooks_owner_id", "owner_id"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookVisibility.PRIVATE.value,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookStatus.DRAFT.value,
    )


class LorebookEntry(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "lorebook_entries"
    __table_args__ = (
        CheckConstraint(
            (
                "entry_type IN ("
                "'author_note', 'world', 'genre', 'rule', 'location', 'faction', "
                "'character_relation', 'event', 'term', 'secret'"
                ")"
            ),
            name="ck_lorebook_entries_entry_type",
        ),
        CheckConstraint(
            "activation_type IN ('always', 'keyword', 'semantic', 'manual')",
            name="ck_lorebook_entries_activation_type",
        ),
        CheckConstraint(
            "match_mode IN ('exact', 'contains', 'regex')",
            name="ck_lorebook_entries_match_mode",
        ),
        CheckConstraint(
            (
                "placement IN ("
                "'system_top', 'before_memory', 'after_memory', "
                "'before_history', 'near_user_message'"
                ")"
            ),
            name="ck_lorebook_entries_placement",
        ),
        Index("ix_lorebook_entries_lorebook_id", "lorebook_id"),
        Index(
            "ix_lorebook_entries_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 100},
        ),
    )

    lorebook_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("lorebooks.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookEntryType.WORLD.value,
    )
    activation_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookEntryActivationType.KEYWORD.value,
    )
    key_triggers: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    match_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookEntryMatchMode.CONTAINS.value,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    token_budget: Mapped[int | None] = mapped_column(Integer)
    placement: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=LorebookEntryPlacement.BEFORE_HISTORY.value,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
