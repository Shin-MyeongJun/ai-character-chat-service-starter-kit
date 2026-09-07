from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import UUID

import pytest
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.modules.lorebook import repository, types
from app.modules.lorebook.service import query
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

pytestmark = pytest.mark.asyncio


def uid(value: int) -> UUID:
    # SQLite treats an all-numeric PostgreSQL UUID column as numeric affinity.
    return UUID(int=(0xA << 124) + value)


def make_lorebook(value: int, owner_id: UUID, created_at: datetime) -> Lorebook:
    return Lorebook(
        id=uid(value),
        owner_id=owner_id,
        title=f"Lorebook {value}",
        description=f"Description {value}",
        visibility="private" if value == 10 else "public",
        status="draft" if value == 10 else "approved",
        created_at=created_at,
        updated_at=created_at,
    )


def make_entry(
    value: int,
    *,
    lorebook_id: UUID | None = None,
    activation_type: str = "keyword",
    key_triggers: list[str] | None = None,
    match_mode: str = "contains",
    priority: int = 0,
    is_enabled: bool = True,
) -> LorebookEntry:
    created_at = datetime(2026, 9, 1, tzinfo=UTC) + timedelta(minutes=value)
    return LorebookEntry(
        id=uid(value),
        lorebook_id=lorebook_id or uid(10),
        title=f"Entry {value}",
        content=f"Content {value}",
        entry_type="world",
        activation_type=activation_type,
        key_triggers=key_triggers,
        match_mode=match_mode,
        priority=priority,
        token_budget=128,
        placement="before_history",
        is_enabled=is_enabled,
        metadata_={"value": value},
        created_at=created_at,
        updated_at=created_at,
    )


class AsyncScalarsAdapter:
    """Run async repository SELECT calls through a synchronous SQLite session."""

    def __init__(self, session: Session) -> None:
        self.sync_session = session

    async def scalars(self, statement):
        return self.sync_session.scalars(statement)


@pytest.fixture
def data():
    older = datetime(2026, 9, 1, tzinfo=UTC)
    newer = older + timedelta(days=1)
    owner_id = uid(800)
    other_owner_id = uid(801)
    lorebooks = [
        make_lorebook(10, owner_id, older),
        make_lorebook(20, other_owner_id, newer),
        make_lorebook(30, owner_id, newer),
        make_lorebook(40, owner_id, newer),
        make_lorebook(50, other_owner_id, older - timedelta(days=1)),
    ]
    return SimpleNamespace(
        lorebooks=lorebooks,
        owner_id=owner_id,
        other_owner_id=other_owner_id,
    )


@pytest.fixture
def database(data):
    engine = create_engine("sqlite://")
    # LorebookEntry uses PostgreSQL-only ARRAY, JSONB, and Vector columns, so only
    # the parent table is exercised through real SQL in this query test module.
    with engine.begin() as connection:
        connection.execute(CreateTable(Lorebook.__table__))
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(data.lorebooks)
        session.commit()
        yield AsyncScalarsAdapter(session)
    engine.dispose()


async def test_lorebook_cursor_pages_include_private_rows_and_handle_timestamp_ties(
    database,
):
    seen = []
    cursor = None

    while True:
        page = await query.list_lorebooks(database, cursor=cursor, limit=2)
        assert isinstance(page, types.LorebookPage)
        assert all(isinstance(item, types.LorebookInfo) for item in page.items)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
        assert cursor.id == page.items[-1].id
        assert cursor.created_at == page.items[-1].created_at
        assert len(seen) <= 5, "The cursor must advance without repeating rows"

    assert seen == [uid(value) for value in (40, 30, 20, 10, 50)]


async def test_owner_filter_is_preserved_across_lorebook_cursor_pages(database, data):
    first = await query.list_lorebooks_by_owner_id(
        database,
        owner_id=data.owner_id,
        limit=2,
    )
    second = await query.list_lorebooks_by_owner_id(
        database,
        owner_id=data.owner_id,
        cursor=first.next_cursor,
        limit=2,
    )

    assert [item.id for item in first.items] == [uid(40), uid(30)]
    assert [item.id for item in second.items] == [uid(10)]
    assert all(item.owner_id == data.owner_id for item in first.items + second.items)
    assert second.next_cursor is None


async def test_lorebook_detail_is_owner_scoped(database, data):
    result = await query.get_lorebook_by_id(database, lorebook_id=uid(10))
    owned = await query.get_lorebook_by_id_and_owner_id(
        database,
        lorebook_id=uid(10),
        owner_id=data.owner_id,
    )
    foreign = await query.get_lorebook_by_id_and_owner_id(
        database,
        lorebook_id=uid(10),
        owner_id=data.other_owner_id,
    )

    assert isinstance(result, types.LorebookInfo)
    assert result == owned
    assert result.visibility == "private"
    assert result.status == "draft"
    assert foreign is None
    assert await query.get_lorebook_by_id(database, lorebook_id=uid(999)) is None


async def test_entry_page_forwards_parent_cursor_and_limit(monkeypatch):
    cursor = types.LorebookCursor(
        created_at=datetime(2026, 9, 2, tzinfo=UTC),
        id=uid(201),
    )
    entries = [make_entry(101), make_entry(102)]
    repository_page = types.LorebookEntryPage(items=entries, next_cursor=cursor)
    list_entries = AsyncMock(return_value=repository_page)
    monkeypatch.setattr(repository, "list_lorebook_entries", list_entries)
    session = object()

    page = await query.list_lorebook_entries(
        session,
        lorebook_id=uid(10),
        cursor=cursor,
        limit=7,
    )

    list_entries.assert_awaited_once_with(session, uid(10), cursor=cursor, limit=7)
    assert [item.id for item in page.items] == [uid(101), uid(102)]
    assert all(isinstance(item, types.LorebookEntryInfo) for item in page.items)
    assert page.next_cursor is cursor


async def test_owned_entry_list_checks_parent_before_reading_children(monkeypatch):
    parent = make_lorebook(
        10,
        uid(800),
        datetime(2026, 9, 1, tzinfo=UTC),
    )
    get_parent = AsyncMock(side_effect=[None, parent])
    list_entries = AsyncMock(
        return_value=types.LorebookEntryPage(
            items=[make_entry(101)],
            next_cursor=None,
        )
    )
    monkeypatch.setattr(repository, "get_lorebook_by_id_and_owner_id", get_parent)
    monkeypatch.setattr(repository, "list_lorebook_entries", list_entries)
    session = object()

    denied = await query.list_lorebook_entries_by_owner_id(
        session,
        lorebook_id=uid(10),
        owner_id=uid(801),
    )
    assert denied is None
    list_entries.assert_not_awaited()

    page = await query.list_lorebook_entries_by_owner_id(
        session,
        lorebook_id=uid(10),
        owner_id=uid(800),
        limit=3,
    )

    assert [item.id for item in page.items] == [uid(101)]
    assert get_parent.await_args_list == [
        call(session, uid(10), uid(801)),
        call(session, uid(10), uid(800)),
    ]
    list_entries.assert_awaited_once_with(
        session,
        uid(10),
        cursor=None,
        limit=3,
    )


async def test_entry_lookup_keeps_entry_id_scoped_to_requested_parent(monkeypatch):
    entry = make_entry(101, lorebook_id=uid(10))

    async def scoped_lookup(session, entry_id, lorebook_id):
        if entry_id == uid(101) and lorebook_id == uid(10):
            return entry
        return None

    get_entry = AsyncMock(side_effect=scoped_lookup)
    monkeypatch.setattr(repository, "get_lorebook_entry", get_entry)
    session = object()

    owned = await query.get_lorebook_entry(
        session,
        lorebook_id=uid(10),
        entry_id=uid(101),
    )
    cross_parent = await query.get_lorebook_entry(
        session,
        lorebook_id=uid(20),
        entry_id=uid(101),
    )

    assert isinstance(owned, types.LorebookEntryInfo)
    assert owned.lorebook_id == uid(10)
    assert cross_parent is None
    assert get_entry.await_args_list == [
        call(session, uid(101), uid(10)),
        call(session, uid(101), uid(20)),
    ]


async def test_owned_entry_lookup_stops_on_parent_owner_mismatch(monkeypatch):
    parent = make_lorebook(
        10,
        uid(800),
        datetime(2026, 9, 1, tzinfo=UTC),
    )
    entry = make_entry(101, lorebook_id=uid(10))
    get_parent = AsyncMock(side_effect=[None, parent])
    get_entry = AsyncMock(return_value=entry)
    monkeypatch.setattr(repository, "get_lorebook_by_id_and_owner_id", get_parent)
    monkeypatch.setattr(repository, "get_lorebook_entry", get_entry)
    session = object()

    denied = await query.get_lorebook_entry_by_owner_id(
        session,
        lorebook_id=uid(10),
        entry_id=uid(101),
        owner_id=uid(801),
    )
    assert denied is None
    get_entry.assert_not_awaited()

    owned = await query.get_lorebook_entry_by_owner_id(
        session,
        lorebook_id=uid(10),
        entry_id=uid(101),
        owner_id=uid(800),
    )

    assert isinstance(owned, types.LorebookEntryInfo)
    get_entry.assert_awaited_once_with(session, uid(101), uid(10))


async def test_always_activation_requests_enabled_rows_and_preserves_order(monkeypatch):
    high = make_entry(101, activation_type="always", priority=100)
    low = make_entry(102, activation_type="always", priority=1)
    list_enabled = AsyncMock(return_value=[high, low])
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        list_enabled,
    )
    session = object()

    active = await query.get_always_entries(
        session,
        lorebook_ids=[uid(10), uid(20), uid(10)],
    )

    # Enabled filtering and priority ordering are repository contracts. The query
    # selects that repository operation and carries its order into prompt entries.
    list_enabled.assert_awaited_once_with(session, [uid(10), uid(20)], "always")
    assert [item.entry_id for item in active] == [uid(101), uid(102)]
    assert all(isinstance(item, types.ActiveLorebookEntry) for item in active)


@pytest.mark.parametrize(
    ("match_mode", "trigger", "text", "matches"),
    [
        ("exact", "Dragon", "dragon", True),
        ("exact", "Dragon", "the dragon", False),
        ("contains", "Dragon", "The DRAGON wakes", True),
        ("contains", "Dragon", "A wyvern wakes", False),
        ("regex", r"\bdragons?\b", "Two DRAGONS wake", True),
        ("regex", r"^dragon$", "dragon wakes", False),
    ],
)
async def test_keyword_activation_match_modes_are_case_insensitive(
    monkeypatch,
    match_mode,
    trigger,
    text,
    matches,
):
    entry = make_entry(
        101,
        key_triggers=[trigger],
        match_mode=match_mode,
    )
    list_enabled = AsyncMock(return_value=[entry])
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        list_enabled,
    )
    session = object()

    active = await query.activate_keyword_entries(
        session,
        lorebook_ids=[uid(10), uid(10)],
        text=text,
    )

    list_enabled.assert_awaited_once_with(session, [uid(10)], "keyword")
    assert [item.entry_id for item in active] == ([uid(101)] if matches else [])


async def test_keyword_activation_preserves_repository_order_of_matching_rows(
    monkeypatch,
):
    first = make_entry(
        101,
        key_triggers=["dragon"],
        match_mode="contains",
        priority=100,
    )
    skipped = make_entry(
        102,
        key_triggers=["castle"],
        match_mode="contains",
        priority=50,
    )
    second = make_entry(
        103,
        key_triggers=[r"dragons?"],
        match_mode="regex",
        priority=1,
    )
    list_enabled = AsyncMock(return_value=[first, skipped, second])
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        list_enabled,
    )

    active = await query.activate_keyword_entries(
        object(),
        lorebook_ids=[uid(10)],
        text="A dragon wakes",
    )

    assert [item.entry_id for item in active] == [uid(101), uid(103)]


async def test_empty_keyword_text_skips_repository_lookup(monkeypatch):
    list_enabled = AsyncMock()
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        list_enabled,
    )

    assert (
        await query.activate_keyword_entries(
            object(),
            lorebook_ids=[uid(10)],
            text="",
        )
        == []
    )
    list_enabled.assert_not_awaited()


async def test_invalid_stored_keyword_regex_raises_domain_error(monkeypatch):
    entry = make_entry(101, key_triggers=["["], match_mode="regex")
    list_enabled = AsyncMock(return_value=[entry])
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        list_enabled,
    )

    with pytest.raises(ValueError, match="invalid regular expression"):
        await query.activate_keyword_entries(
            object(),
            lorebook_ids=[uid(10)],
            text="dragon",
        )
