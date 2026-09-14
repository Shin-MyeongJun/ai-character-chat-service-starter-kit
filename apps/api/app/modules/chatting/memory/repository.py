"""Memory persistence. Services own policy; callers own transactions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import cast, get_args
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Select, case, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Conversation
from app.db.models.memory import ConversationMemory, MemoryJob
from app.db.pagination import fetch_cursor_page
from app.modules.chatting.memory import types as Types

DEFAULT_MEMORY_LIST_LIMIT = 50
MAX_MEMORY_LIST_LIMIT = 100
MAX_MEMORY_SEARCH_LIMIT = 100
MEMORY_EMBEDDING_DIMENSION = cast(
    int, cast(Vector, ConversationMemory.__table__.c.embedding.type).dim
)


@dataclass(frozen=True)
class MemoryPageRow:
    items: list[ConversationMemory]
    next_cursor: Types.MemoryCursor | None


def _scoped_select(
    conversation_id: UUID, owner_id: UUID
) -> Select[tuple[ConversationMemory]]:
    return (
        select(ConversationMemory)
        .join(Conversation, Conversation.id == ConversationMemory.conversation_id)
        .where(
            ConversationMemory.conversation_id == conversation_id,
            Conversation.user_id == owner_id,
        )
    )


def validate_memory_types(memory_types: Sequence[Types.MemoryType] | None) -> None:
    if memory_types is not None and any(
        item not in get_args(Types.MemoryType) for item in memory_types
    ):
        raise ValueError("Invalid memory type.")


async def conversation_is_owned(
    session: AsyncSession, *, conversation_id: UUID, owner_id: UUID
) -> bool:
    return (
        await session.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id, Conversation.user_id == owner_id
            )
        )
        is not None
    )


async def delete_conversation_memories(session, conversation_id) -> None:
    await session.execute(
        delete(ConversationMemory).where(
            ConversationMemory.conversation_id == conversation_id
        )
    )


async def delete_memory_job(session, conversation_id) -> None:
    await session.execute(
        delete(MemoryJob).where(MemoryJob.conversation_id == conversation_id)
    )


async def create_memory(session, memory: ConversationMemory) -> ConversationMemory:
    session.add(memory)
    await session.flush()
    await session.refresh(memory)
    return memory


async def update_memory(session, memory: ConversationMemory) -> ConversationMemory:
    session.add(memory)
    await session.flush()
    await session.refresh(memory)
    return memory


async def delete_memory(session, memory: ConversationMemory) -> None:
    await session.delete(memory)
    await session.flush()


async def get_memory(
    session: AsyncSession,
    *,
    memory_id: UUID,
    conversation_id: UUID,
    owner_id: UUID,
    for_update: bool = False,
) -> ConversationMemory | None:
    stmt = _scoped_select(conversation_id, owner_id).where(
        ConversationMemory.id == memory_id
    )
    if for_update:
        stmt = stmt.with_for_update(of=ConversationMemory)
    return (await session.scalars(stmt)).one_or_none()


async def list_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    cursor: Types.MemoryCursor | None = None,
    limit: int = DEFAULT_MEMORY_LIST_LIMIT,
    memory_types: Sequence[Types.MemoryType] | None = None,
) -> MemoryPageRow:
    validate_memory_types(memory_types)
    stmt = _scoped_select(conversation_id, owner_id)
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    return await fetch_cursor_page(
        session,
        stmt,
        created_at=ConversationMemory.created_at,
        id_column=ConversationMemory.id,
        cursor=cursor,
        limit=limit,
        max_limit=MAX_MEMORY_LIST_LIMIT,
        cursor_factory=Types.MemoryCursor,
        page_factory=MemoryPageRow,
    )


async def get_latest_summary(
    session: AsyncSession, *, conversation_id: UUID, owner_id: UUID
) -> ConversationMemory | None:
    return await session.scalar(
        _scoped_select(conversation_id, owner_id)
        .where(ConversationMemory.memory_type == "summary")
        .order_by(
            ConversationMemory.source_end_position.desc().nullslast(),
            ConversationMemory.created_at.desc(),
            ConversationMemory.id.desc(),
        )
        .limit(1)
    )


async def get_pending_index(
    session: AsyncSession, *, conversation_id: UUID, owner_id: UUID
) -> ConversationMemory | None:
    return await session.scalar(
        _scoped_select(conversation_id, owner_id)
        .where(
            ConversationMemory.memory_type == "summary",
            ConversationMemory.index_status.in_(("pending", "failed")),
        )
        .order_by(
            ConversationMemory.source_end_position.asc().nullsfirst(),
            ConversationMemory.created_at,
            ConversationMemory.id,
        )
        .limit(1)
    )


async def create_summary(
    session: AsyncSession, *, generated: Types.GeneratedSummaryInfo, importance: float
) -> ConversationMemory:
    plan = generated.plan
    identity = (
        ConversationMemory.conversation_id == plan.conversation_id,
        ConversationMemory.memory_type == "summary",
        ConversationMemory.source_start_position == plan.source_start_position,
        ConversationMemory.source_end_position == plan.source_end_position,
        ConversationMemory.conversation_revision == plan.conversation_revision,
        ConversationMemory.prompt_version == plan.prompt_version,
    )
    entity = await session.scalar(
        insert(ConversationMemory)
        .values(
            conversation_id=plan.conversation_id,
            memory_type="summary",
            content=generated.content,
            index_status="pending",
            importance=importance,
            summary_provider=generated.provider.value,
            summary_model=generated.model,
            prompt_version=plan.prompt_version,
            source_start_position=plan.source_start_position,
            source_end_position=plan.source_end_position,
            source_digest=plan.source_digest,
            conversation_revision=plan.conversation_revision,
            summary_input_tokens=generated.input_tokens,
            summary_output_tokens=generated.output_tokens,
        )
        .on_conflict_do_nothing(constraint="uq_conversation_memory_summary_source")
        .returning(ConversationMemory)
    )
    if entity is None:
        entity = await session.scalar(select(ConversationMemory).where(*identity))
    if entity is None:
        raise RuntimeError("Summary upsert did not return its durable row.")
    return entity


async def save_embedding(
    session: AsyncSession, *, value: Types.EmbeddedSummaryInfo
) -> ConversationMemory | None:
    return await session.scalar(
        update(ConversationMemory)
        .where(
            ConversationMemory.id == value.memory_id,
            ConversationMemory.conversation_revision == value.conversation_revision,
            ConversationMemory.index_status.in_(("pending", "failed")),
        )
        .values(
            embedding=list(value.vector),
            embedding_provider=value.provider.value,
            embedding_model=value.model,
            embedding_dimension=value.dimension,
            embedding_settings=value.settings,
            embedded_content_digest=value.content_digest,
            embedding_tokens=value.total_tokens,
            index_status="ready",
        )
        .returning(ConversationMemory)
        .execution_options(populate_existing=True)
    )


async def has_searchable_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    embedding_provider: str | None,
    embedding_model: str,
    embedding_dimension: int,
    memory_types: Sequence[Types.MemoryType] | None,
) -> bool:
    validate_memory_types(memory_types)
    stmt = _scoped_select(conversation_id, owner_id).where(
        ConversationMemory.index_status == "ready",
        ConversationMemory.embedding.is_not(None),
        ConversationMemory.embedding_model == embedding_model,
        ConversationMemory.embedding_dimension == embedding_dimension,
    )
    if embedding_provider is not None:
        stmt = stmt.where(ConversationMemory.embedding_provider == embedding_provider)
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    return (
        await session.scalar(stmt.with_only_columns(ConversationMemory.id).limit(1))
        is not None
    )


async def search_memories(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    owner_id: UUID,
    query_embedding: Sequence[float],
    embedding_provider: str,
    embedding_model: str,
    top_k: int = 5,
    memory_types: Sequence[Types.MemoryType] | None = None,
) -> list[tuple[ConversationMemory, float]]:
    validate_memory_types(memory_types)
    if not 1 <= top_k <= MAX_MEMORY_SEARCH_LIMIT:
        raise ValueError(f"top_k must be between 1 and {MAX_MEMORY_SEARCH_LIMIT}.")
    if not isinstance(embedding_provider, str) or not embedding_provider.strip():
        raise ValueError("embedding_provider must be a non-blank string.")
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise ValueError("embedding_model must be a non-blank string.")
    vector = list(query_embedding)
    if len(vector) != MEMORY_EMBEDDING_DIMENSION or not all(
        isfinite(v) for v in vector
    ):
        raise ValueError(
            f"Query embedding must contain {MEMORY_EMBEDDING_DIMENSION} finite values."
        )
    if not any(vector):
        raise ValueError("Cosine search requires a nonzero query embedding.")
    distance = ConversationMemory.embedding.cosine_distance(vector)
    stmt = (
        _scoped_select(conversation_id, owner_id)
        .add_columns(distance.label("distance"))
        .where(
            ConversationMemory.index_status == "ready",
            ConversationMemory.embedding.is_not(None),
            ConversationMemory.embedding_provider == embedding_provider,
            ConversationMemory.embedding_model == embedding_model,
            ConversationMemory.embedding_dimension == len(vector),
        )
    )
    if memory_types is not None:
        stmt = stmt.where(ConversationMemory.memory_type.in_(memory_types))
    rows = (await session.execute(stmt.order_by(distance).limit(top_k))).all()
    return [
        (entity, 1.0 - float(value))
        for entity, value in rows
        if value is not None and isfinite(value)
    ]


async def schedule_memory_work(
    session: AsyncSession, *, conversation_id: UUID, owner_id: UUID, now: datetime
) -> None:
    stmt = insert(MemoryJob).values(
        conversation_id=conversation_id,
        owner_id=owner_id,
        requested_generation=1,
        completed_generation=0,
        status="pending",
        next_attempt_at=now,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=(MemoryJob.conversation_id,),
            set_={
                "owner_id": owner_id,
                "requested_generation": MemoryJob.requested_generation + 1,
                "status": case(
                    (MemoryJob.status == "running", "running"), else_="pending"
                ),
                "attempt_count": case(
                    (MemoryJob.status == "failed", 0), else_=MemoryJob.attempt_count
                ),
                "next_attempt_at": case(
                    (MemoryJob.status == "running", MemoryJob.next_attempt_at),
                    else_=now,
                ),
                "last_error_kind": None,
                "updated_at": now,
            },
        )
    )


async def claim_memory_work(
    session: AsyncSession, *, worker_id: str, now: datetime, lease_seconds: int
) -> MemoryJob | None:
    eligible = or_(
        (MemoryJob.status == "pending") & (MemoryJob.next_attempt_at <= now),
        (MemoryJob.status == "running") & (MemoryJob.leased_until < now),
    )
    job = await session.scalar(
        select(MemoryJob)
        .where(eligible)
        .order_by(
            MemoryJob.next_attempt_at, MemoryJob.updated_at, MemoryJob.conversation_id
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.scope_generation = job.requested_generation
    job.lease_owner = worker_id
    job.leased_until = now + timedelta(seconds=lease_seconds)
    job.attempt_count += 1
    job.updated_at = now
    await session.flush()
    return job


async def complete_memory_work(
    session: AsyncSession,
    *,
    work: Types.MemoryWorkInfo,
    more_work: bool,
    now: datetime,
) -> MemoryJob | None:
    status = (
        "pending"
        if more_work
        else case(
            (MemoryJob.requested_generation > work.scope_generation, "pending"),
            else_="idle",
        )
    )
    values = {
        "completed_generation": work.scope_generation,
        "status": status,
        "attempt_count": 0,
        "lease_owner": None,
        "leased_until": None,
        "scope_generation": None,
        "next_attempt_at": now,
        "last_error_kind": None,
        "updated_at": now,
    }
    return await session.scalar(
        update(MemoryJob)
        .where(
            MemoryJob.conversation_id == work.conversation_id,
            MemoryJob.status == "running",
            MemoryJob.lease_owner == work.lease_owner,
            MemoryJob.scope_generation == work.scope_generation,
        )
        .values(**values)
        .returning(MemoryJob)
    )


async def fail_memory_work(
    session: AsyncSession,
    *,
    work: Types.MemoryWorkInfo,
    retryable: bool,
    max_attempts: int,
    retry_seconds: int,
    error_kind: str,
    now: datetime,
) -> MemoryJob | None:
    should_retry = retryable and work.attempt_count < max_attempts
    return await session.scalar(
        update(MemoryJob)
        .where(
            MemoryJob.conversation_id == work.conversation_id,
            MemoryJob.status == "running",
            MemoryJob.lease_owner == work.lease_owner,
            MemoryJob.scope_generation == work.scope_generation,
        )
        .values(
            status="pending" if should_retry else "failed",
            lease_owner=None,
            leased_until=None,
            scope_generation=None,
            next_attempt_at=now + timedelta(seconds=retry_seconds),
            last_error_kind=error_kind[:100],
            updated_at=now,
        )
        .returning(MemoryJob)
    )
