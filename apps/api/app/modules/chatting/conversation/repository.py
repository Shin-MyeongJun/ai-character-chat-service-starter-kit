# 대화와 참여자·버전 전환 이력의 저장소. 참여자는 role_order, id 순으로 반환한다.
# 전환은 참여자 목록을 교체하고 active_model_id를 비운다. start_set_id와 initial_snapshot_id는 유지한다.
from collections.abc import Sequence
from datetime import datetime
from typing import TypeAlias
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import (
    Conversation,
    ConversationCharacter,
    ConversationVersionChange,
)
from app.modules.chatting.conversation import types as Types

ConversationStatisticsRows: TypeAlias = tuple[
    list[tuple[UUID | None, int]], list[tuple[UUID, int]]
]


async def get_owned_conversation(
    session: AsyncSession, conversation_id: UUID, user_id: UUID, *, lock: bool = False
) -> Conversation | None:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    conversation: Conversation | None = await session.scalar(stmt)
    return conversation


async def list_owned_conversations(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int,
    cursor_created_at: datetime | None = None,
    cursor_id: UUID | None = None,
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.user_id == user_id)
    if cursor_created_at is not None:
        # The query service requires cursor timestamp and ID together.
        assert cursor_id is not None
        stmt = stmt.where(
            or_(
                Conversation.created_at < cursor_created_at,
                and_(
                    Conversation.created_at == cursor_created_at,
                    Conversation.id < cursor_id,
                ),
            )
        )
    return list(
        await session.scalars(
            stmt.order_by(Conversation.created_at.desc(), Conversation.id.desc()).limit(
                limit + 1
            )
        )
    )


async def count_owned_conversations(session: AsyncSession, user_id: UUID) -> int:
    """Count the exact owner scope used by the directory, including empty rooms."""
    count = await session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.user_id == user_id)
    )
    # COUNT without GROUP BY returns one non-null row, including empty scopes.
    assert count is not None
    return count


async def advance_history_revision(
    session: AsyncSession, conversation_id: UUID
) -> Conversation | None:
    conversation: Conversation | None = await session.scalar(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(history_revision=Conversation.history_revision + 1)
        .returning(Conversation)
        .execution_options(populate_existing=True)
    )
    return conversation


async def list_conversation_characters(
    session: AsyncSession, conversation_id: UUID
) -> list[ConversationCharacter]:
    return list(
        await session.scalars(
            select(ConversationCharacter)
            .where(ConversationCharacter.conversation_id == conversation_id)
            .order_by(ConversationCharacter.role_order, ConversationCharacter.id)
        )
    )


async def create_conversation(
    session: AsyncSession, command: Types.CreateConversationCommand
) -> Conversation:
    conversation = Conversation(
        id=uuid4(),
        user_id=command.user_id,
        product_id=command.product_id,
        product_snapshot_id=command.snapshot_id,
        initial_snapshot_id=command.snapshot_id,
        start_set_id=command.start_set_id,
        is_group=len(command.characters) > 1,
        title=command.title,
        opening_mode="snapshot",
    )
    session.add(conversation)
    await session.flush()
    for character in command.characters:
        session.add(
            ConversationCharacter(
                conversation_id=conversation.id,
                character_id=character.character_id,
                product_character_id=character.product_character_id,
                role_order=character.role_order,
            )
        )
    return conversation


async def switch_conversation_version(
    session: AsyncSession,
    conversation_id: UUID,
    current_id: UUID,
    target_id: UUID,
    characters: Sequence[Types.ConversationCharacterCommand],
    mode: str,
    changed_at: datetime,
) -> None:
    conversation = await session.get(Conversation, conversation_id)
    await session.execute(
        delete(ConversationCharacter).where(
            ConversationCharacter.conversation_id == conversation_id
        )
    )
    for character in characters:
        session.add(
            ConversationCharacter(
                conversation_id=conversation_id,
                character_id=character.character_id,
                product_character_id=character.product_character_id,
                role_order=character.role_order,
            )
        )
    session.add(
        ConversationVersionChange(
            created_at=changed_at,
            conversation_id=conversation_id,
            from_snapshot_id=current_id,
            to_snapshot_id=target_id,
            mode=mode,
        )
    )
    # The owning command already obtained the conversation's FOR UPDATE lock.
    assert conversation is not None
    conversation.product_snapshot_id = target_id
    conversation.is_group = len(characters) > 1
    conversation.active_model_id = None
    await session.flush()


async def get_statistics_facts(
    session: AsyncSession, product_id: UUID, start: datetime, end: datetime
) -> ConversationStatisticsRows:
    conversations = list(
        (
            await session.execute(
                select(Conversation.initial_snapshot_id, func.count())
                .where(
                    Conversation.product_id == product_id,
                    Conversation.initial_snapshot_id.is_not(None),
                    Conversation.created_at >= start,
                    Conversation.created_at < end,
                )
                .group_by(Conversation.initial_snapshot_id)
            )
        ).tuples()
    )
    change = ConversationVersionChange
    transitions = list(
        (
            await session.execute(
                select(change.to_snapshot_id, func.count())
                .join(Conversation, Conversation.id == change.conversation_id)
                .where(
                    Conversation.product_id == product_id,
                    change.created_at >= start,
                    change.created_at < end,
                )
                .group_by(change.to_snapshot_id)
            )
        ).tuples()
    )
    return conversations, transitions
