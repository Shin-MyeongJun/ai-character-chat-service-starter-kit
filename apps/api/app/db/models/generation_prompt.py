"""Chat-owned, immutable pre-adapter prompt snapshots; never SDK HTTP bodies."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GenerationPrompt(Base):
    __tablename__ = "generation_prompts"
    __table_args__ = (
        CheckConstraint("format_version = 1", name="ck_generation_prompt_format"),
        CheckConstraint(
            "digest ~ '^[0-9a-f]{64}$'", name="ck_generation_prompt_digest"
        ),
        CheckConstraint("max_output_tokens > 0", name="ck_generation_prompt_output"),
    )

    generation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_generations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(Text, nullable=False)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
