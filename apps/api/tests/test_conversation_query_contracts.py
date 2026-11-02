"""Offline conversation scopes, fact boundaries and preserved mapper values."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    Uuid,
    create_engine,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.models.chat import (
    Conversation,
    ConversationCharacter,
    ConversationVersionChange,
)
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types
from app.modules.chatting.conversation.mapper import persistence as Mapper
from app.modules.chatting.conversation.service import query as QueryService
from app.modules.content.character import types as CharacterTypes
from app.modules.content.product import types as ProductTypes
from app.modules.llm import types as LlmTypes


@pytest.fixture
def database():
    metadata = MetaData()
    defaults = {
        "id": "(lower(hex(randomblob(16))))",
        "created_at": "CURRENT_TIMESTAMP",
        "updated_at": "CURRENT_TIMESTAMP",
        "history_revision": "1",
        "opening_mode": "'legacy_messages'",
        "is_group": "false",
    }
    for model in (Conversation, ConversationCharacter, ConversationVersionChange):
        Table(
            model.__tablename__,
            metadata,
            *[
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                    server_default=text(defaults[column.name])
                    if column.name in defaults
                    else None,
                )
                for column in model.__table__.columns
            ],
        )
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            for name in ("scalar", "scalars", "execute", "get", "flush"):
                getattr(session, name).side_effect = getattr(sync_session, name)
            session.add.side_effect = sync_session.add
            yield sync_session, session
    finally:
        engine.dispose()


def conversation(owner_id, product_id, index, created_at, **fields):
    return Conversation(
        id=UUID(int=index),
        user_id=owner_id,
        product_id=product_id,
        created_at=created_at,
        updated_at=created_at,
        **fields,
    )


@pytest.mark.asyncio
async def test_owner_page_uses_timestamp_id_ties_and_count_includes_empty_rooms(
    database,
):
    sync_session, session = database
    owner_id, other_id, product_id = uuid4(), uuid4(), uuid4()
    stamp = datetime(2026, 10, 28, tzinfo=UTC)
    sync_session.add_all(
        [
            conversation(
                owner_id,
                product_id,
                index,
                stamp,
                title=None if index == 1 else "Pinned title",
            )
            for index in (1, 2, 3)
        ]
        + [conversation(other_id, product_id, 4, stamp)]
    )
    sync_session.flush()
    command = types.ListOwnedConversationsCommand(user_id=owner_id, limit=1)
    first = await QueryService.list_owned_conversations(session, command)
    assert [item.id for item in first.items] == [UUID(int=3)]
    second = await QueryService.list_owned_conversations(
        session,
        replace(
            command,
            cursor_created_at=first.next_cursor_created_at.replace(tzinfo=UTC),
            cursor_id=first.next_cursor_id,
        ),
    )
    assert [item.id for item in second.items] == [UUID(int=2)]
    final = await QueryService.list_owned_conversations(
        session,
        replace(
            command,
            cursor_created_at=second.next_cursor_created_at.replace(tzinfo=UTC),
            cursor_id=second.next_cursor_id,
        ),
    )
    assert final.items[0].id == UUID(int=1) and final.items[0].title is None
    assert final.next_cursor_id is final.next_cursor_created_at is None
    assert (
        await QueryService.count_owned_conversations(session, replace(command, limit=0))
        == 3
    )
    empty = types.ListOwnedConversationsCommand(user_id=uuid4())
    assert (await QueryService.list_owned_conversations(session, empty)).items == ()
    assert await QueryService.count_owned_conversations(session, empty) == 0


@pytest.mark.asyncio
async def test_locked_lookup_refreshes_and_participants_keep_nullable_ids_and_order(
    database,
):
    sync_session, session = database
    owner_id, product_id = uuid4(), uuid4()
    stamp = datetime(2026, 10, 28, tzinfo=UTC)
    entity = conversation(owner_id, product_id, 10, stamp)
    sync_session.add(entity)
    sync_session.flush()
    sync_session.execute(
        update(Conversation)
        .where(Conversation.id == entity.id)
        .values(history_revision=4)
        .execution_options(synchronize_session=False)
    )
    assert entity.history_revision == 1
    command = types.OwnedConversationCommand(
        conversation_id=entity.id, user_id=owner_id, lock=True
    )
    info = await QueryService.get_owned_conversation(session, command)
    assert info.history_revision == 4 and info.product_snapshot_id is None
    sync_session.add_all(
        [
            ConversationCharacter(
                id=UUID(int=index),
                conversation_id=entity.id,
                character_id=None,
                product_character_id=None,
                role_order=order,
            )
            for index, order in ((3, 1), (2, 0), (1, 0))
        ]
    )
    rows = await Repository.list_conversation_characters(session, entity.id)
    assert [row.id for row in rows] == [UUID(int=1), UUID(int=2), UUID(int=3)]
    participants = await QueryService.list_conversation_characters(session, command)
    assert [item.role_order for item in participants] == [0, 0, 1]
    assert all(
        item.character_id is item.product_character_id is None for item in participants
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_unauthorized_or_missing_conversation_never_reads_participants(
    database, monkeypatch, missing
):
    sync_session, session = database
    owner_id, product_id = uuid4(), uuid4()
    entity = conversation(owner_id, product_id, 10, datetime(2026, 10, 28, tzinfo=UTC))
    sync_session.add(entity)
    sync_session.flush()
    lookup = AsyncMock()
    monkeypatch.setattr(Repository, "list_conversation_characters", lookup)
    command = types.OwnedConversationCommand(
        conversation_id=uuid4() if missing else entity.id,
        user_id=owner_id if missing else uuid4(),
    )
    with pytest.raises(LookupError, match="Conversation not found"):
        await QueryService.list_conversation_characters(session, command)
    lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"limit": 0},
        {"limit": 101},
        {"cursor_id": uuid4()},
        {"cursor_created_at": datetime(2026, 10, 28, tzinfo=UTC)},
        {"cursor_created_at": datetime(2026, 10, 28), "cursor_id": uuid4()},
    ],
)
async def test_invalid_cursor_is_rejected_before_repository(monkeypatch, fields):
    lookup = AsyncMock()
    monkeypatch.setattr(Repository, "list_owned_conversations", lookup)
    async with AsyncSession() as session:
        with pytest.raises(ValueError, match="Invalid conversation cursor or limit"):
            await QueryService.list_owned_conversations(
                session, types.ListOwnedConversationsCommand(user_id=uuid4(), **fields)
            )
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_history_and_switch_keep_initial_start_and_replace_participant_slots(
    database,
):
    sync_session, session = database
    owner_id, product_id, initial_id, target_id, start_id, slot_id = [
        uuid4() for _ in range(6)
    ]
    command = types.CreateConversationCommand(
        owner_id,
        product_id,
        initial_id,
        start_id,
        "Pinned",
        (types.ConversationCharacterCommand(None, slot_id, 0),),
    )
    entity = await Repository.create_conversation(session, command)
    assert entity.initial_snapshot_id == entity.product_snapshot_id == initial_id
    assert (
        entity.opening_mode == "snapshot"
        and entity.start_set_id == start_id
        and not entity.is_group
    )
    assert (
        await Repository.advance_history_revision(session, entity.id)
    ).history_revision == 2
    entity.active_model_id = uuid4()
    next_slots = [uuid4(), uuid4()]
    await Repository.switch_conversation_version(
        session,
        entity.id,
        initial_id,
        target_id,
        tuple(
            types.ConversationCharacterCommand(None, slot, order)
            for order, slot in enumerate(next_slots)
        ),
        "choice",
        datetime(2026, 10, 28, tzinfo=UTC),
    )
    assert entity.product_snapshot_id == target_id and entity.is_group
    assert entity.initial_snapshot_id == initial_id and entity.start_set_id == start_id
    assert entity.history_revision == 2 and entity.active_model_id is None
    assert [
        row.product_character_id
        for row in await Repository.list_conversation_characters(session, entity.id)
    ] == next_slots
    change = sync_session.scalars(select(ConversationVersionChange)).one()
    assert (change.from_snapshot_id, change.to_snapshot_id, change.mode) == (
        initial_id,
        target_id,
        "choice",
    )
    assert await Repository.advance_history_revision(session, uuid4()) is None


@pytest.mark.asyncio
async def test_statistics_facts_keep_product_scope_initial_version_and_half_open_times(
    database,
):
    sync_session, session = database
    owner_id, product_id, other_product, initial_id, target_id = [
        uuid4() for _ in range(5)
    ]
    start = datetime(2026, 10, 28, tzinfo=UTC)
    end = start + timedelta(days=1)
    rooms = [
        conversation(
            owner_id,
            product_id,
            1,
            start,
            initial_snapshot_id=initial_id,
            product_snapshot_id=target_id,
        ),
        conversation(
            uuid4(),
            product_id,
            2,
            end - timedelta(microseconds=1),
            initial_snapshot_id=initial_id,
        ),
        conversation(owner_id, product_id, 3, start, initial_snapshot_id=None),
        conversation(owner_id, product_id, 4, end, initial_snapshot_id=target_id),
        conversation(
            owner_id,
            product_id,
            5,
            start - timedelta(microseconds=1),
            initial_snapshot_id=target_id,
        ),
        conversation(owner_id, other_product, 6, start, initial_snapshot_id=initial_id),
    ]
    sync_session.add_all(rooms)
    sync_session.flush()
    sync_session.add_all(
        [
            ConversationVersionChange(
                conversation_id=room.id,
                from_snapshot_id=initial_id,
                to_snapshot_id=target_id,
                mode="choice",
                created_at=stamp,
            )
            for room, stamp in (
                (rooms[0], start),
                (rooms[1], end - timedelta(microseconds=1)),
                (rooms[2], end),
                (rooms[-1], start),
            )
        ]
    )
    info = await QueryService.get_statistics_facts(
        session, types.GetStatisticsFactsCommand(product_id, start, end)
    )
    assert info.conversations == [(initial_id, 2)] and info.transitions == [
        (target_id, 2)
    ]
    assert type(info.conversations[0]) is type(info.transitions[0]) is tuple
    assert await QueryService.get_statistics_facts(
        session, types.GetStatisticsFactsCommand(uuid4(), start, end)
    ) == types.ConversationStatisticsInfo([], [])


def snapshot_values():
    (
        product_id,
        snapshot_id,
        slot_id,
        character_snapshot_id,
        book_slot,
        book_snapshot,
        source_id,
    ) = [uuid4() for _ in range(7)]
    snapshot = ProductTypes.ProductSnapshotInfo(
        snapshot_id,
        product_id,
        1,
        {
            "title": "Pinned",
            "opening_message": "Global",
            "extension": {"preserved": [1]},
            "studio_start_options": {str(source_id): {"opening": "Scene"}},
        },
        None,
        None,
    )
    runtime = ProductTypes.SnapshotRuntimeView(
        ProductTypes.SnapshotCompositionInfo(
            [
                ProductTypes.SnapshotCharacterInfo(
                    id=slot_id,
                    character_snapshot_id=character_snapshot_id,
                    role_order=0,
                    role_name=None,
                    is_primary=True,
                )
            ],
            [
                ProductTypes.SnapshotLorebookInfo(
                    book_slot, book_snapshot, "main", 0, True, "selected"
                )
            ],
            [
                ProductTypes.ProductLorebookTargetInfo(
                    product_character_id=slot_id, product_lorebook_id=book_slot
                )
            ],
            [],
        ),
        {
            character_snapshot_id: CharacterTypes.CharacterSnapshotInfo(
                character_snapshot_id, None, 1, {"name": "Archived"}
            )
        },
        {},
    )
    return snapshot, runtime, source_id


def test_runtime_mapper_distinguishes_slots_preserves_json_references_and_nullable_start():
    snapshot, runtime, _source_id = snapshot_values()
    owner_id, start_id = uuid4(), uuid4()
    command = Mapper.snapshot_runtime_view_to_create_command(
        runtime, snapshot, owner_id, snapshot.product_id, start_id
    )
    assert command.title == "Pinned" and command.snapshot_id == snapshot.id
    assert command.characters[0].character_id is None
    assert (
        command.characters[0].product_character_id
        == runtime.composition.characters[0].id
    )
    conversation_info = types.ConversationInfo(
        uuid4(),
        owner_id,
        snapshot.product_id,
        snapshot.id,
        None,
        None,
        datetime.now(UTC),
    )
    start = types.ConversationStartView(None, "legacy_messages", None, None, (), None)
    entries = {
        runtime.composition.books[0].lorebook_snapshot_id: [
            {"id": "lore", "content": "Pinned"}
        ]
    }
    execution = LlmTypes.ExecutionView(uuid4(), "provider", "model", "low", False, None)
    result = Mapper.conversation_snapshot_infos_to_runtime_view(
        conversation_info, snapshot, runtime, execution, entries, start
    )
    assert result.start is result.opening_message is None
    assert (
        "opening_message" not in result.settings
        and "studio_start_options" not in result.settings
    )
    assert result.settings["extension"] is snapshot.snapshot_data["extension"]
    assert (
        result.characters[0].data
        is runtime.characters[
            runtime.composition.characters[0].character_snapshot_id
        ].snapshot_data
    )
    assert (
        result.lorebooks[0].entries
        is entries[runtime.composition.books[0].lorebook_snapshot_id]
    )
    assert result.lorebooks[0].targets == [
        str(command.characters[0].product_character_id)
    ]


@pytest.mark.parametrize(
    ("mode", "opening", "expected"),
    [
        ("snapshot", "Scene", "Scene"),
        ("snapshot", "", ""),
        ("snapshot", None, None),
        ("legacy_messages", "Scene", None),
    ],
)
def test_start_mapper_keeps_scene_opening_empty_null_and_legacy(
    mode, opening, expected
):
    snapshot, _runtime, source_id = snapshot_values()
    snapshot.snapshot_data["studio_start_options"][str(source_id)]["opening"] = opening
    info = types.ConversationInfo(
        uuid4(),
        uuid4(),
        snapshot.product_id,
        snapshot.id,
        snapshot.id,
        uuid4(),
        datetime.now(UTC),
        opening_mode=mode,
    )
    start = ProductTypes.SnapshotStartInfo(
        info.start_set_id, source_id, None, "Start", 0
    )
    result = Mapper.conversation_start_infos_to_view(info, snapshot, start, (), None)
    assert result.opening_message == expected and result.start.title is None
    assert result.initial_snapshot_id == snapshot.id


def test_start_mapper_preserves_legacy_absence_fallback_and_missing_default_error():
    snapshot, _runtime, source_id = snapshot_values()
    info = types.ConversationInfo(
        uuid4(), uuid4(), snapshot.product_id, None, None, None, datetime.now(UTC)
    )
    legacy = Mapper.conversation_start_infos_to_view(info, None, None, (), None)
    assert legacy.opening_message is legacy.start is None
    start = ProductTypes.SnapshotStartInfo(uuid4(), uuid4(), "Title", "Start", 0)
    verified = replace(info, opening_mode="snapshot", initial_snapshot_id=snapshot.id)
    assert (
        Mapper.conversation_start_infos_to_view(
            verified, snapshot, start, (), None
        ).opening_message
        == "Global"
    )
    snapshot.snapshot_data.pop("opening_message")
    with pytest.raises(KeyError, match="opening_message"):
        Mapper.conversation_start_infos_to_view(
            verified, snapshot, replace(start, source_entry_id=source_id), (), None
        )
