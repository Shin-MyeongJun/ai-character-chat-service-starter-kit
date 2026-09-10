from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Literal, TypeAlias, TypeVar
from uuid import UUID

# Keep aligned with the database constraint; manual/pinned semantics are deferred.
MemoryType: TypeAlias = Literal["summary", "fact", "event"]


@dataclass(frozen=True, slots=True)
class CreateMemoryCommand:
    conversation_id: UUID
    memory_type: MemoryType
    content: str
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class UpdateMemoryCommand:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class DeleteMemoryCommand:
    conversation_id: UUID
    memory_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True)
class SearchMemoriesCommand:
    conversation_id: UUID
    query_text: str  # 서비스가 내부적으로 임베딩 변환
    owner_id: UUID  # 서비스에서 대화 접근 권한 검증에 사용
    top_k: int = 5
    memory_types: tuple[MemoryType, ...] | None = None  # 필요시 fact/event만 검색 등


@dataclass(frozen=True, slots=True)
class RetrievedMemoryInfo:
    memory_id: UUID
    memory_type: MemoryType
    content: str
    similarity_score: float  # 프롬프트 조립 시 임계값 필터링/디버깅용


@dataclass(frozen=True, slots=True)
class MemoryInfo:
    id: UUID
    conversation_id: UUID
    memory_type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MemoryCursor:
    created_at: datetime
    id: UUID


TMemoryItem = TypeVar("TMemoryItem")


@dataclass(frozen=True, slots=True)
class MemoryPage(Generic[TMemoryItem]):
    items: list[TMemoryItem]
    next_cursor: MemoryCursor | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetMemoryCommand:
    memory_id: UUID
    conversation_id: UUID
    owner_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMemoriesCommand:
    conversation_id: UUID
    owner_id: UUID
    cursor: MemoryCursor | None = None
    limit: int = 50
    memory_types: Sequence[MemoryType] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetLatestSummaryCommand:
    conversation_id: UUID
    owner_id: UUID
