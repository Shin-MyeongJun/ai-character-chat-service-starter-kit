# provider 활성화, 모델 context_window(토큰 수), capability와 종료 일정을 저장한다.
# 가격 필드는 현재 답변의 cost_credit 계산에 연결되어 있지 않다. 단가 기준은 이 스키마만으로 확정하지 않는다.
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models._mixins import TimestampMixin, UuidPkMixin


class Provider(UuidPkMixin, Base):
    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class Model(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint(
            "provider_id", "model_name", name="uq_models_provider_model_name"
        ),
    )

    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False)
    input_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    output_price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    capabilities: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    retirement_announced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    shutdown_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelReplacement(UuidPkMixin, Base):
    __tablename__ = "model_replacements"
    __table_args__ = (
        UniqueConstraint(
            "product_snapshot_id",
            "from_model_id",
            "to_model_id",
            name="uq_model_replacement",
        ),
    )
    product_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("product_snapshots.id"), nullable=False
    )
    from_model_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("models.id"), nullable=False
    )
    to_model_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("models.id"), nullable=False
    )
    reasoning_effort: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
