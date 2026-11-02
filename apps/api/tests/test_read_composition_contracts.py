"""Offline directory SQL pagination, ownership, live cursors and HTTP values."""

from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Select,
    Table,
    Text,
    Uuid,
    create_engine,
    delete,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.http.mapper.conversation_directory import recent_conversations_page_to_response
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as ChatTypes
from app.modules.chatting.conversation import types as ConversationTypes
from app.use_cases import conversation_directory as Service


@dataclass
class DirectoryFixture:
    owner: UUID
    created: datetime
    active: datetime
    store: Session
    session: AsyncMock
    conversations: Table
    messages: Table
    delivered_rows: list[int]

    def add_room(self, number: int, *, owner: UUID | None = None) -> None:
        self.store.execute(
            self.conversations.insert().values(
                id=UUID(int=number),
                user_id=owner or self.owner,
                product_id=UUID(int=10),
                title=None,
                created_at=self.created,
            )
        )

    def add_message(self, room: int, position: int, content: str, at: datetime) -> None:
        self.store.execute(
            self.messages.insert().values(
                id=UUID(int=position),
                conversation_id=UUID(int=room),
                position=position,
                content=content,
                created_at=at,
            )
        )

    async def page(
        self,
        *,
        limit: int = 30,
        at: datetime | None = None,
        cursor: UUID | None = None,
        owner: UUID | None = None,
    ) -> Service.RecentConversationsPageView:
        return await Service.list_recent_conversations(
            self.session,
            ConversationTypes.ListOwnedConversationsCommand(
                user_id=owner or self.owner,
                limit=limit,
                cursor_created_at=at,
                cursor_id=cursor,
            ),
        )


@pytest.fixture
def directory() -> Iterator[DirectoryFixture]:
    metadata = MetaData()
    rooms = Table(
        "conversations",
        metadata,
        Column("id", Uuid(native_uuid=False), primary_key=True),
        Column("user_id", Uuid(native_uuid=False)),
        Column("product_id", Uuid(native_uuid=False)),
        Column("title", Text),
        Column("created_at", DateTime(timezone=True)),
    )
    messages = Table(
        "messages",
        metadata,
        Column("id", Uuid(native_uuid=False), primary_key=True),
        Column("conversation_id", Uuid(native_uuid=False)),
        Column("content", Text),
        Column("created_at", DateTime(timezone=True)),
        Column("position", Integer),
    )
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    delivered: list[int] = []
    try:
        with Session(engine) as store:
            session = AsyncMock(spec=AsyncSession)

            def execute(
                statement: Select[Repository.RecentConversationValues],
            ) -> list[Repository.RecentConversationValues]:
                rows = list(store.execute(statement))
                delivered.append(len(rows))
                # SQLite drops UTC tzinfo; PostgreSQL returns aware timestamps.
                # Adapt only result timezones, never ordering, predicates or paging.
                return [
                    (
                        row[0],
                        row[1],
                        row[2],
                        row[3].replace(tzinfo=UTC),
                        row[4],
                        row[5].replace(tzinfo=UTC),
                    )
                    for row in rows
                ]

            session.execute.side_effect = execute
            session.scalar.side_effect = store.scalar
            created = datetime(2026, 10, 28, tzinfo=UTC)
            item = DirectoryFixture(
                UUID(int=99),
                created,
                created + timedelta(hours=1),
                store,
                session,
                rooms,
                messages,
                delivered,
            )
            for number in (1, 2, 3):
                item.add_room(number)
            item.add_room(4, owner=UUID(int=100))
            item.add_message(2, 1, "최근 메시지", item.active)
            item.add_message(3, 2, "최근 메시지", item.active)
            item.add_message(
                4, 3, "other owner's secret", item.active + timedelta(days=1)
            )
            yield item
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_activity_cursor_and_total_use_db_pages_and_keep_empty_rooms(
    directory: DirectoryFixture,
) -> None:
    item = directory
    first = await item.page(limit=1)
    second = await item.page(
        limit=1, at=first.next_cursor_created_at, cursor=first.next_cursor_id
    )
    last = await item.page(
        limit=1, at=second.next_cursor_created_at, cursor=second.next_cursor_id
    )
    assert [page.items[0].id.int for page in (first, second, last)] == [3, 2, 1]
    assert [page.total for page in (first, second, last)] == [3, 3, 3]
    assert (first.next_cursor_created_at, first.next_cursor_id) == (
        item.active,
        UUID(int=3),
    )
    assert (last.next_cursor_created_at, last.next_cursor_id) == (None, None)
    assert last.items[0].last_message is None
    assert last.items[0].last_activity_at == last.items[0].created_at
    assert item.delivered_rows == [2, 2, 1]
    assert item.session.execute.await_count == item.session.scalar.await_count == 3
    response = recent_conversations_page_to_response(first)
    assert response.total == 3 and response.items[0].last_message == "최근 메시지"
    assert response.items[0].last_activity_at == item.active
    assert response.items[0].title is None and response.next_cursor_id == UUID(int=3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limit,cursor_created_at,cursor_id",
    [
        (0, None, None),
        (101, None, None),
        (30, None, UUID(int=1)),
        (30, datetime(2026, 10, 28, tzinfo=UTC), None),
        (30, datetime(2026, 10, 28), UUID(int=1)),
    ],
)
async def test_invalid_activity_cursor_fails_before_public_reads(
    directory: DirectoryFixture,
    limit: int,
    cursor_created_at: datetime | None,
    cursor_id: UUID | None,
) -> None:
    with pytest.raises(ValueError, match="Invalid activity cursor or limit"):
        await directory.page(limit=limit, at=cursor_created_at, cursor=cursor_id)
    directory.session.execute.assert_not_awaited()
    directory.session.scalar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [1, 7, 100])
async def test_large_owner_scope_fetches_only_page_plus_one_in_two_statements(
    directory: DirectoryFixture, limit: int
) -> None:
    item = directory
    for number in range(10, 360):
        item.add_room(number)
    page = await item.page(limit=limit)
    assert page.total == 353 and len(page.items) == limit
    assert item.delivered_rows == [limit + 1]
    item.session.scalar.assert_awaited_once()
    item.session.execute.assert_awaited_once()
    statement = item.session.execute.await_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert f"LIMIT {limit + 1}" in sql and "FOR UPDATE" not in sql
    assert "messages.created_at DESC, messages.position DESC" in sql
    assert "conversations.user_id =" in sql
    assert "coalesce(" in sql
    assert page.next_cursor_id is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("tied_time", [False, True])
async def test_latest_preview_uses_timestamp_before_position_and_position_breaks_ties(
    directory: DirectoryFixture, tied_time: bool
) -> None:
    item = directory
    item.add_message(
        2, 100, "older despite position", item.active - timedelta(seconds=1)
    )
    item.add_message(2, 9, "latest", item.active)
    item.add_message(
        2,
        10,
        "tied position winner" if tied_time else "newer timestamp winner",
        item.active if tied_time else item.active + timedelta(seconds=1),
    )
    page = await item.page()
    room = next(room for room in page.items if room.id == UUID(int=2))
    assert room.last_message == (
        "tied position winner" if tied_time else "newer timestamp winner"
    )
    assert room.last_activity_at == (
        item.active if tied_time else item.active + timedelta(seconds=1)
    )
    if not tied_time:
        assert page.items[0].id == room.id


@pytest.mark.asyncio
async def test_empty_preview_is_not_an_empty_room_and_deleted_messages_recompute_activity(
    directory: DirectoryFixture,
) -> None:
    item = directory
    item.add_message(2, 10, "", item.active + timedelta(hours=1))
    page = await item.page()
    assert page.items[0].last_message == "" and page.items[0].id == UUID(int=2)
    item.store.execute(delete(item.messages).where(item.messages.c.id == UUID(int=10)))
    page = await item.page()
    assert page.items[0].id == UUID(int=3)
    room = next(room for room in page.items if room.id == UUID(int=2))
    assert room.last_message == "최근 메시지" and room.last_activity_at == item.active
    item.store.execute(
        delete(item.messages).where(item.messages.c.conversation_id == UUID(int=2))
    )
    page = await item.page()
    room = next(room for room in page.items if room.id == UUID(int=2))
    assert room.last_message is None and room.last_activity_at == item.created
    assert page.total == 3


@pytest.mark.asyncio
async def test_message_time_before_room_creation_is_preserved_without_greatest(
    directory: DirectoryFixture,
) -> None:
    item = directory
    item.store.execute(
        delete(item.messages).where(item.messages.c.conversation_id == UUID(int=2))
    )
    item.add_message(2, 10, "imported old message", item.created - timedelta(days=1))
    page = await item.page()
    assert [room.id.int for room in page.items] == [3, 1, 2]
    assert page.items[-1].last_activity_at == item.created - timedelta(days=1)


@pytest.mark.asyncio
async def test_empty_owner_and_cursor_past_end_have_correct_total(
    directory: DirectoryFixture,
) -> None:
    item = directory
    empty = await item.page(owner=UUID(int=999))
    assert not empty.items and empty.total == 0
    past_end = await item.page(at=item.created - timedelta(days=1), cursor=UUID(int=1))
    assert not past_end.items and past_end.total == 3
    assert empty.next_cursor_id is past_end.next_cursor_id is None
    assert empty.next_cursor_created_at is past_end.next_cursor_created_at is None


@pytest.mark.asyncio
async def test_cursor_row_can_be_deleted_without_requiring_it_to_exist(
    directory: DirectoryFixture,
) -> None:
    item = directory
    first = await item.page(limit=1)
    item.store.execute(
        delete(item.messages).where(
            item.messages.c.conversation_id == first.next_cursor_id
        )
    )
    item.store.execute(
        delete(item.conversations).where(
            item.conversations.c.id == first.next_cursor_id
        )
    )
    second = await item.page(
        at=first.next_cursor_created_at, cursor=first.next_cursor_id
    )
    assert [room.id.int for room in second.items] == [2, 1] and second.total == 2


@pytest.mark.asyncio
async def test_live_activity_can_move_before_existing_cursor_until_refresh(
    directory: DirectoryFixture,
) -> None:
    item = directory
    first = await item.page(limit=1)
    item.add_message(1, 10, "new activity", item.active + timedelta(hours=1))
    second = await item.page(
        at=first.next_cursor_created_at, cursor=first.next_cursor_id
    )
    assert [room.id.int for room in second.items] == [2] and second.total == 3
    refreshed = await item.page(limit=1)
    assert refreshed.items[0].id == UUID(int=1)


@pytest.mark.asyncio
async def test_compatibility_entry_point_preserves_command_and_view_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = Service.RecentConversationsPageView(
        items=(), next_cursor_created_at=None, next_cursor_id=None
    )
    assert page.total == 0
    room = Service.RecentConversationView(
        UUID(int=1), UUID(int=2), None, datetime.now(UTC), None
    )
    assert room.last_activity_at is None
    reader = AsyncMock(return_value=page)
    monkeypatch.setattr(Service.ChatViewsService, "list_recent_conversations", reader)
    at = datetime(2026, 10, 29, tzinfo=UTC) + timedelta(hours=1)
    command = ConversationTypes.ListOwnedConversationsCommand(
        UUID(int=99), 7, at, UUID(int=1)
    )
    async with AsyncSession() as session:
        assert await Service.list_recent_conversations(session, command) is page
        reader.assert_awaited_once_with(
            session,
            ChatTypes.ListRecentConversationsCommand(
                user_id=command.user_id,
                limit=7,
                cursor_activity_at=at,
                cursor_id=command.cursor_id,
            ),
        )
    assert replace(room, last_activity_at=at).last_activity_at == at
