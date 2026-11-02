# 소유 대화의 현재 선형 이력을 조회한다. 페이지 사이 편집까지 고정한 스냅샷 조회는 아니다.
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.chatting.memory import service as MemoryService


async def list_messages(
    session: AsyncSession, command: Types.ListMessagesCommand
) -> Types.MessagePageInfo:
    if type(command.limit) is not int or not 1 <= command.limit <= 100:
        raise ValueError("Page limit must be 1–100.")
    if command.cursor and (
        command.cursor.conversation_id != command.conversation_id
        or type(command.cursor.position) is not int
        or not 0 < command.cursor.position < 2**63
    ):
        raise ValueError("Invalid message cursor.")
    conversation = await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    rows = await Repository.list_messages(
        session,
        command.conversation_id,
        command.cursor.position if command.cursor else 0,
        command.limit,
    )
    return PersistenceMapper.messages_entities_to_page_info(
        rows,
        command.conversation_id,
        command.limit,
        history_revision=conversation.history_revision,
        after_cursor=command.cursor,
    )


async def list_conversation_previews(
    session: AsyncSession, command: Types.ListConversationPreviewsCommand
) -> dict[UUID, str]:
    if len(command.conversation_ids) > 100:
        raise ValueError("Too many conversation previews.")
    rows = await Repository.list_latest_message_previews(
        session, command.user_id, command.conversation_ids
    )
    return PersistenceMapper.conversation_preview_rows_to_info(rows)


async def list_conversation_activity(
    session: AsyncSession, command: Types.ListConversationPreviewsCommand
) -> dict[UUID, Types.ConversationActivityInfo]:
    """Expose chat-owned activity for an owner-scoped batch of at most 100 rooms."""
    if len(command.conversation_ids) > 100:
        raise ValueError("Too many conversation activities.")
    return PersistenceMapper.conversation_activity_rows_to_info(
        await Repository.list_conversation_activity(
            session, command.user_id, command.conversation_ids
        )
    )


async def list_memory_source(
    session: AsyncSession, command: Types.ListMemorySourceCommand
) -> Types.MemorySourceInfo:
    if (
        type(command.after_position) is not int
        or command.after_position < 0
        or command.through_position is not None
        and (
            type(command.through_position) is not int
            or command.through_position <= command.after_position
        )
        or type(command.limit) is not int
        or not 1 <= command.limit <= 10000
    ):
        raise ValueError("Invalid internal memory source range.")
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    rows = await Repository.list_message_range(
        session,
        command.conversation_id,
        command.after_position,
        command.through_position,
        command.limit,
    )
    return PersistenceMapper.messages_entities_to_memory_source_info(
        rows, command.limit
    )


async def get_history_version(
    session: AsyncSession, command: Types.GetHistoryVersionCommand
) -> Types.HistoryVersionInfo:
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    return PersistenceMapper.history_version_to_info(
        await Repository.get_history_version(session, command.conversation_id)
    )


async def list_recent_messages(
    session: AsyncSession, command: Types.ListRecentMessagesCommand
) -> tuple[Types.MessageInfo, ...]:
    if type(command.limit) is not int or not 1 <= command.limit <= 100:
        raise ValueError("Recent message limit must be 1–100.")
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    source = PersistenceMapper.messages_entities_to_memory_source_info(
        await Repository.list_message_range(
            session,
            command.conversation_id,
            0,
            None,
            command.limit,
            newest_first=True,
        ),
        command.limit,
    )
    return tuple(reversed(source.messages))


async def read_message_window(
    session: AsyncSession, command: Types.ReadMessageWindowCommand
) -> Types.MessageWindowInfo:
    """Read a contiguous prefix/suffix through the first token-budget overflow.

    Keep that whole overflow message as evidence for compaction. Page size bounds
    transfer overshoot; total retained text depends on budget, not conversation age.
    The caller owns a conversation lock when several reads must share one history.
    """
    if (
        type(command.token_budget) is not int
        or command.token_budget < 0
        or type(command.after_position) is not int
        or command.after_position < 0
        or command.through_position is not None
        and (
            type(command.through_position) is not int
            or command.through_position <= command.after_position
        )
        or type(command.minimum_messages) is not int
        or not 0 <= command.minimum_messages <= 100
    ):
        raise ValueError("Invalid message window budget or range.")
    await get_owned_conversation(
        session,
        ConversationTypes.OwnedConversationCommand(
            conversation_id=command.conversation_id, user_id=command.user_id
        ),
    )
    after, through = command.after_position, command.through_position
    messages: list[Types.MessageInfo] = []
    used_tokens = 0
    has_more = False
    while True:
        page = PersistenceMapper.messages_entities_to_memory_source_info(
            await Repository.list_message_range(
                session,
                command.conversation_id,
                after,
                through,
                128,
                newest_first=command.newest_first,
            ),
            128,
        )
        for index, item in enumerate(page.messages):
            messages.append(item)
            if item.id != command.excluded_message_id:
                used_tokens += MemoryService.estimate_message_tokens(
                    item.sender_type,
                    item.content,
                    conservative=command.conservative_token_budget,
                )
            if (
                used_tokens > command.token_budget
                and len(messages) >= command.minimum_messages
            ):
                has_more = page.truncated or index < len(page.messages) - 1
                break
        else:
            if page.truncated:
                if command.newest_first:
                    through = page.messages[-1].position - 1
                else:
                    after = page.messages[-1].position
                continue
            break
        break
    if command.newest_first:
        messages.reverse()
    return Types.MessageWindowInfo(tuple(messages), has_more)
