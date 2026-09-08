from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

Visibility = Literal["private", "public", "unlisted"]


@dataclass(frozen=True, slots=True)
class ProductWrite:
    title: str
    description: str | None = None
    opening_message: str | None = None
    visibility: Visibility = "private"


@dataclass(frozen=True, slots=True)
class ProductInfo:
    id: UUID
    title: str
    description: str | None
    opening_message: str | None
    visibility: str
    status: str
    created_at: datetime
    updated_at: datetime
