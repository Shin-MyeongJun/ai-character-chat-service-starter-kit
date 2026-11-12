# messages·요청 receipt·생성 사실의 저장소. 대화 소유권과 쓰기 잠금은 상위 서비스가 확보한다.
# 메시지 조회는 position 오름차순, 경계 초과만 선택하고 limit+1로 다음 페이지/잘림을 판정한다.
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import TypeAlias, cast
from uuid import UUID, uuid4

from sqlalchemy import (
    CursorResult,
    Row,
    Select,
    delete,
    func,
    literal_column,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Conversation, Message, MessageRequest
from app.db.models.generation_prompt import GenerationPrompt
from app.db.models.message_history import ChatHistoryVersion
from app.db.models.product_usage import AnswerRecoveryAttempt, ProductGeneration
from app.modules.chatting.chat import types as Types
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.llm import types as LlmTypes

ConversationPreviewRow: TypeAlias = Row[tuple[UUID, str]] | tuple[UUID, str]
ConversationActivityRow: TypeAlias = (
    Row[tuple[UUID, str, datetime]] | tuple[UUID, str, datetime]
)
RecentConversationValues: TypeAlias = tuple[
    UUID, UUID, str | None, datetime, str | None, datetime
]
RecentConversationRow: TypeAlias = (
    Row[RecentConversationValues] | RecentConversationValues
)
GenerationCountRow: TypeAlias = (
    Row[tuple[UUID, str, int, int]] | tuple[UUID, str, int, int]
)
GenerationUserRow: TypeAlias = Row[tuple[UUID, UUID]] | tuple[UUID, UUID]
GenerationStatisticsRows: TypeAlias = tuple[
    Iterable[GenerationCountRow], Iterable[GenerationUserRow]
]
GenerationStatusCountRow: TypeAlias = Row[tuple[str, int]] | tuple[str, int]
GenerationPromptSummaryValues: TypeAlias = tuple[
    UUID,
    UUID,
    UUID,
    str,
    str,
    str,
    datetime,
    datetime | None,
    datetime | None,
    bool,
    datetime | None,
    str | None,
]
GenerationPromptSummaryRow: TypeAlias = Row[GenerationPromptSummaryValues]


async def has_pending_generation(session: AsyncSession, conversation_id: UUID) -> bool:
    return (
        await session.scalar(
            select(ProductGeneration.id)
            .where(
                ProductGeneration.conversation_id == conversation_id,
                ProductGeneration.status == "pending",
            )
            .limit(1)
        )
        is not None
    )


async def get_message(
    session: AsyncSession, conversation_id: UUID, message_id: UUID | None
) -> Message | None:
    message: Message | None = await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.id == message_id)
        .execution_options(populate_existing=True)
    )
    return message


async def get_last_message(
    session: AsyncSession, conversation_id: UUID
) -> Message | None:
    message: Message | None = await session.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.position.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return message


async def list_messages(
    session: AsyncSession, conversation_id: UUID, after: int, limit: int
) -> list[Message]:
    return list(
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.position > after)
            .order_by(Message.position)
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    )


async def list_latest_message_previews(
    session: AsyncSession, user_id: UUID, conversation_ids: Sequence[UUID]
) -> list[Row[tuple[UUID, str]]]:
    if not conversation_ids:
        return []
    return list(
        await session.execute(
            select(Message.conversation_id, Message.content)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.conversation_id.in_(conversation_ids),
            )
            .distinct(Message.conversation_id)
            .order_by(Message.conversation_id, Message.position.desc())
        )
    )


async def list_conversation_activity(
    session: AsyncSession, user_id: UUID, conversation_ids: Sequence[UUID]
) -> list[Row[tuple[UUID, str, datetime]]]:
    """Read latest surviving message activity; Conversation is only an ownership scope."""
    return (
        list(
            await session.execute(
                select(Message.conversation_id, Message.content, Message.created_at)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.user_id == user_id,
                    Message.conversation_id.in_(conversation_ids),
                )
                .distinct(Message.conversation_id)
                .order_by(
                    Message.conversation_id,
                    Message.created_at.desc(),
                    Message.position.desc(),
                )
            )
        )
        if conversation_ids
        else []
    )


async def list_recent_conversations(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor_activity_at: datetime | None = None,
    cursor_id: UUID | None = None,
) -> list[Row[RecentConversationValues]]:
    """Explicit read-projection exception; see architecture rule C.2.

    Only page-sized metadata/previews cross the DB boundary. The database still
    evaluates activity across the owner's scope to sort it; this is not O(limit).
    """
    latest_created_at = (
        select(Message.created_at)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc(), Message.position.desc())
        .limit(1)
        .scalar_subquery()
    )
    activity_at = func.coalesce(latest_created_at, Conversation.created_at)
    statement = select(
        Conversation.id,
        Conversation.product_id,
        Conversation.title,
        Conversation.created_at,
        activity_at.label("last_activity_at"),
    ).where(Conversation.user_id == user_id)
    if cursor_activity_at is not None:
        assert cursor_id is not None  # The service validates the cursor pair.
        statement = statement.where(
            (activity_at < cursor_activity_at)
            | ((activity_at == cursor_activity_at) & (Conversation.id < cursor_id))
        )
    page = (
        statement.order_by(activity_at.desc(), Conversation.id.desc())
        .limit(limit + 1)
        .subquery()
    )
    # Fetch content only for the selected page; use the same timestamp/position
    # rule as activity selection, within this single statement's read snapshot.
    preview = (
        select(Message.content)
        .where(Message.conversation_id == page.c.id)
        .order_by(Message.created_at.desc(), Message.position.desc())
        .limit(1)
        .scalar_subquery()
    )
    result = await session.execute(
        select(
            page.c.id,
            page.c.product_id,
            page.c.title,
            page.c.created_at,
            preview,
            page.c.last_activity_at,
        ).order_by(page.c.last_activity_at.desc(), page.c.id.desc())
    )
    return list(result)


async def list_message_range(
    session: AsyncSession,
    conversation_id: UUID,
    after: int,
    through: int | None,
    limit: int,
    *,
    newest_first: bool = False,
) -> list[Message]:
    stmt = select(Message).where(
        Message.conversation_id == conversation_id, Message.position > after
    )
    if through is not None:
        stmt = stmt.where(Message.position <= through)
    return list(
        await session.scalars(
            stmt.order_by(Message.position.desc() if newest_first else Message.position)
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    )


async def get_history_version(session: AsyncSession, conversation_id: UUID) -> int:
    version = await session.scalar(
        select(ChatHistoryVersion.version).where(
            ChatHistoryVersion.conversation_id == conversation_id
        )
    )
    # New empty conversations have no stamp until the first message INSERT.
    return version if version is not None else 0


async def get_message_request(
    session: AsyncSession, conversation_id: UUID, request_key: str
) -> MessageRequest | None:
    return await session.get(
        MessageRequest, (conversation_id, request_key), populate_existing=True
    )


async def create_message(
    session: AsyncSession,
    command: Types.CreateMessageCommand,
    snapshot_id: UUID | None,
    sender_type: str,
    character_id: UUID | None,
    product_character_id: UUID | None,
    digest: str,
) -> Message:
    message = Message(
        conversation_id=command.conversation_id,
        content=command.content,
        sender_type=sender_type,
        character_id=character_id,
        product_character_id=product_character_id,
        product_snapshot_id=snapshot_id,
        generated_by_ai=False,
    )
    session.add(message)
    await session.flush()
    session.add(
        MessageRequest(
            conversation_id=command.conversation_id,
            request_key=command.request_key,
            input_digest=digest,
            message_id=message.id,
        )
    )
    await session.flush()
    return message


async def replace_message(
    session: AsyncSession, message_id: UUID, content: str
) -> Message | None:
    message: Message | None = await session.scalar(
        update(Message)
        .where(Message.id == message_id)
        .values(
            content=content,
            content_blocks=None,
            revision=Message.revision + 1,
            generation_id=None,
            generated_by_ai=False,
            model_id=None,
            token_count=None,
            emotion_tag=None,
        )
        .returning(Message)
        .execution_options(populate_existing=True)
    )
    return message


async def delete_messages_from(
    session: AsyncSession, conversation_id: UUID, position: int
) -> int:
    result = await session.execute(
        delete(Message).where(
            Message.conversation_id == conversation_id, Message.position >= position
        )
    )
    # AsyncSession.execute's general Result annotation does not expose rowcount.
    # A DELETE without RETURNING yields a DBAPI CursorResult on this path.
    return cast(CursorResult[tuple[()]], result).rowcount


async def invalidate_generation_history(
    session: AsyncSession, conversation_id: UUID, now: datetime
) -> None:
    # Execution counters/digests are immutable historical facts. Mark that their
    # original context is no longer the live history, without changing billing.
    await session.execute(
        update(ProductGeneration)
        .where(
            ProductGeneration.conversation_id == conversation_id,
            ProductGeneration.history_invalidated_at.is_(None),
        )
        .values(history_invalidated_at=now)
    )


async def get_generation_by_request(
    session: AsyncSession, user_id: UUID, request_key: str
) -> ProductGeneration | None:
    generation: ProductGeneration | None = await session.scalar(
        select(ProductGeneration).where(
            ProductGeneration.user_id == user_id,
            ProductGeneration.request_key == request_key,
        )
    )
    return generation


async def get_owned_generation(
    session: AsyncSession, generation_id: UUID, user_id: UUID, *, lock: bool = False
) -> ProductGeneration | None:
    stmt = (
        select(ProductGeneration)
        .where(
            ProductGeneration.id == generation_id, ProductGeneration.user_id == user_id
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await session.scalars(stmt)).first()


async def create_generation(
    session: AsyncSession,
    conversation: ConversationTypes.ConversationInfo,
    execution: LlmTypes.ExecutionView,
    user_id: UUID,
    request_key: str,
    digest: str,
    input_text: str,
    input_message_id: UUID | None = None,
) -> ProductGeneration:
    run = ProductGeneration(
        id=uuid4(),
        user_id=user_id,
        conversation_id=conversation.id,
        product_id=conversation.product_id,
        product_snapshot_id=conversation.product_snapshot_id,
        model_id=execution.model_id,
        model_name=execution.model,
        reasoning_effort=execution.reasoning_effort,
        request_key=request_key,
        input_digest=digest,
        status="pending",
        message_count=0,
    )
    session.add(run)
    await session.flush()
    if input_message_id is not None:
        return run
    session.add(
        Message(
            conversation_id=conversation.id,
            product_snapshot_id=run.product_snapshot_id,
            generation_id=run.id,
            sender_type="user",
            content=input_text,
            generated_by_ai=False,
        )
    )
    await session.flush()
    return run


async def update_answer(
    session: AsyncSession,
    generation_id: UUID,
    metadata: Types.AnswerMetadata,
    lease_until: datetime,
) -> None:
    await session.execute(
        update(ProductGeneration)
        .where(ProductGeneration.id == generation_id)
        .values(answer_metadata=metadata, answer_lease_until=lease_until)
    )


async def list_expired_answers(
    session: AsyncSession, now: datetime, limit: int
) -> list[ProductGeneration]:
    return list(
        await session.scalars(
            select(ProductGeneration)
            .where(
                # A fixed internal predicate lets PostgreSQL use the pending
                # partial index even for a prepared statement's generic plan.
                ProductGeneration.status == literal_column("'pending'"),
                ProductGeneration.answer_lease_until <= now,
                ProductGeneration.answer_recovery_quarantined_at.is_(None),
                ProductGeneration.answer_recovery_attempts
                < Types.ANSWER_RECOVERY_MAX_ATTEMPTS,
                or_(
                    ProductGeneration.answer_recovery_next_at.is_(None),
                    ProductGeneration.answer_recovery_next_at <= now,
                ),
            )
            .order_by(ProductGeneration.answer_lease_until)
            .limit(limit)
        )
    )


async def claim_answer_recovery(
    session: AsyncSession,
    command: Types.ClaimAnswerRecoveryCommand,
    attempt_count: int,
    next_at: datetime,
    quarantined_at: datetime | None,
) -> None:
    await session.execute(
        update(ProductGeneration)
        .where(ProductGeneration.id == command.generation_id)
        .values(
            answer_recovery_attempts=attempt_count,
            answer_recovery_next_at=next_at,
            answer_recovery_quarantined_at=quarantined_at,
        )
    )
    session.add(
        AnswerRecoveryAttempt(
            generation_id=command.generation_id,
            attempt_count=attempt_count,
            started_at=command.now,
            operator=command.operator,
            reason=command.reason,
        )
    )
    await session.flush()


async def list_answer_recovery_attempts(
    session: AsyncSession, generation_id: UUID
) -> list[AnswerRecoveryAttempt]:
    return list(
        await session.scalars(
            select(AnswerRecoveryAttempt)
            .where(AnswerRecoveryAttempt.generation_id == generation_id)
            .order_by(AnswerRecoveryAttempt.attempt_count)
        )
    )


async def record_answer_recovery_failure(
    session: AsyncSession,
    command: Types.RecordAnswerRecoveryFailureCommand,
    quarantined_at: datetime | None,
) -> None:
    await session.execute(
        update(AnswerRecoveryAttempt)
        .where(
            AnswerRecoveryAttempt.generation_id == command.generation_id,
            AnswerRecoveryAttempt.attempt_count == command.attempt_count,
        )
        .values(failure_class=command.failure_class)
    )
    await session.execute(
        update(ProductGeneration)
        .where(
            ProductGeneration.id == command.generation_id,
        )
        .values(answer_recovery_quarantined_at=quarantined_at)
    )


async def add_generation_message(
    session: AsyncSession,
    run: Types.GenerationStateInfo,
    output: Types.GeneratedMessage,
    character_id: UUID | None,
    content_blocks: list[Types.AnswerJsonValue] | None = None,
) -> UUID:
    message = Message(
        conversation_id=run.conversation_id,
        product_snapshot_id=run.product_snapshot_id,
        generation_id=run.id,
        product_character_id=output.product_character_id,
        character_id=character_id,
        sender_type="character",
        content=output.content,
        content_blocks=content_blocks,
        model_id=run.model_id,
        generated_by_ai=True,
    )
    session.add(message)
    await session.flush()
    return message.id


async def finish_generation(
    session: AsyncSession,
    generation_id: UUID,
    status: str,
    fingerprint: str,
    now: datetime,
    message_count: int,
    *,
    answer_message_id: UUID | None = None,
) -> ProductGeneration:
    run = await session.get(ProductGeneration, generation_id)
    # The owning command already checked and locked this generation.
    assert run is not None
    run.status, run.result_digest, run.finished_at = status, fingerprint, now
    run.message_count = message_count
    if answer_message_id is not None:
        run.answer_metadata = {
            **(run.answer_metadata or {}),
            "message_id": str(answer_message_id),
        }
    # Lease is live execution ownership, not history. Clear it atomically with
    # every terminal outcome; rollback must retain the pending execution lease.
    run.answer_lease_until = None
    await session.flush()
    return run


async def get_statistics_facts(
    session: AsyncSession, product_id: UUID, start: datetime, end: datetime
) -> GenerationStatisticsRows:
    g = ProductGeneration
    generations = list(
        await session.execute(
            select(
                g.product_snapshot_id, g.status, func.count(), func.sum(g.message_count)
            )
            .where(
                g.product_id == product_id, g.finished_at >= start, g.finished_at < end
            )
            .group_by(g.product_snapshot_id, g.status)
        )
    )
    users = list(
        await session.execute(
            select(g.product_snapshot_id, g.user_id)
            .where(
                g.product_id == product_id,
                g.status == "succeeded",
                g.finished_at >= start,
                g.finished_at < end,
            )
            .distinct()
        )
    )
    return generations, users


async def get_account_generation_statistics(
    session: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> list[Row[tuple[str, int]]]:
    """사용자의 생성 예약 시각 범위 안에서 현재 상태별 건수를 DB에서 집계한다."""
    g = ProductGeneration
    return list(
        (
            await session.execute(
                select(g.status, func.count(g.id))
                .where(g.user_id == user_id, g.created_at >= start, g.created_at < end)
                .group_by(g.status)
            )
        ).all()
    )


async def get_generation_prompt(
    session: AsyncSession, generation_id: UUID
) -> GenerationPrompt | None:
    return await session.get(GenerationPrompt, generation_id, populate_existing=True)


async def create_generation_prompt(
    session: AsyncSession,
    generation_id: UUID,
    *,
    request_json: str,
    digest: str,
    format_version: int,
    provider: str,
    max_output_tokens: int,
) -> None:
    session.add(
        GenerationPrompt(
            generation_id=generation_id,
            request_json=request_json,
            digest=digest,
            format_version=format_version,
            provider=provider,
            max_output_tokens=max_output_tokens,
        )
    )
    await session.flush()


def _select_generation_summaries() -> Select[GenerationPromptSummaryValues]:
    # Deliberately excludes prompt text and answer_metadata even from the SQL projection.
    return select(
        ProductGeneration.id.label("generation_id"),
        ProductGeneration.conversation_id,
        ProductGeneration.model_id,
        ProductGeneration.model_name,
        ProductGeneration.reasoning_effort,
        ProductGeneration.status,
        ProductGeneration.created_at,
        ProductGeneration.finished_at,
        ProductGeneration.history_invalidated_at,
        GenerationPrompt.generation_id.is_not(None).label("prompt_recorded"),
        GenerationPrompt.created_at.label("prompt_created_at"),
        GenerationPrompt.provider,
    ).outerjoin(
        GenerationPrompt, GenerationPrompt.generation_id == ProductGeneration.id
    )


async def list_generation_prompts(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    conversation_id: UUID | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[GenerationPromptSummaryRow], int]:
    predicates = [
        ProductGeneration.created_at >= start,
        ProductGeneration.created_at < end,
    ]
    if conversation_id is not None:
        predicates.append(ProductGeneration.conversation_id == conversation_id)
    if status is not None:
        predicates.append(ProductGeneration.status == status)
    total = await session.scalar(
        select(func.count()).select_from(ProductGeneration).where(*predicates)
    )
    # COUNT without GROUP BY returns one non-null value, including an empty scope.
    assert total is not None
    rows = (
        await session.execute(
            _select_generation_summaries()
            .where(*predicates)
            .order_by(ProductGeneration.created_at.desc(), ProductGeneration.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return rows, total


async def get_generation_prompt_summary(
    session: AsyncSession, generation_id: UUID
) -> GenerationPromptSummaryRow | None:
    return (
        await session.execute(
            _select_generation_summaries().where(ProductGeneration.id == generation_id)
        )
    ).one_or_none()
