# actor_id는 작업을 요청한 관리자, snapshot_id는 상품의 특정 발행 버전이다. expires_at=None은 만료 해제다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ExpiryChange:
    expires_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class ExpiryChangedInfo:
    snapshot_id: UUID
    expires_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True)
class ProductStatusChange:
    status: Literal["draft", "approved", "rejected"]


@dataclass(frozen=True, slots=True)
class ModelRetirement:
    announced_at: datetime
    shutdown_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SetExpiryCommand:
    snapshot_id: UUID
    actor_id: UUID
    expires_at: datetime | None
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ModerateProductCommand:
    product_id: UUID
    actor_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class ModeratedProductInfo:
    product_id: UUID
    status: str
