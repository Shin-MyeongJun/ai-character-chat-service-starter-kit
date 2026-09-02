from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
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
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class Model(TimestampMixin, UuidPkMixin, Base):
    __tablename__ = "models"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_models_provider_model_name"),
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
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
