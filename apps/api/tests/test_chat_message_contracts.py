"""Offline message retry/edit contracts and actual SQL persistence boundaries."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    MetaData,
    Table,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from test_conversation_query_contracts import database as core_database_fixture

from app.db.models.chat import Message, MessageRequest
from app.db.models.generation_prompt import GenerationPrompt
from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types
from app.modules.chatting.chat.mapper import persistence as Mapper
from app.modules.chatting.chat.service.command import messages as Service
from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.llm.types import ExecutionView

core_database = core_database_fixture


def message(conversation_id, **fields):
    values = dict(
        id=uuid4(),
        conversation_id=conversation_id,
        sender_type="user",
        content="Original",
        position=5,
        revision=1,
        created_at=datetime(2026, 10, 28, tzinfo=UTC),
        character_id=None,
        product_character_id=None,
        product_snapshot_id=None,
        generation_id=None,
        generated_by_ai=False,
        model_id=None,
    )
    return Message(**{**values, **fields})


def message_digest(content, slot=None, character=False):
    return hashlib.sha256(
        json.dumps(["character" if character else "user", str(slot), content]).encode()
    ).hexdigest()


@pytest.fixture
def backend(monkeypatch):
    owner_id, conversation_id, product_id, snapshot_id, slot_id = [
        uuid4() for _ in range(5)
    ]
    original = message(conversation_id, product_snapshot_id=snapshot_id)
    updated = message(
        conversation_id,
        id=original.id,
        position=original.position,
        revision=2,
        content="Edited",
        product_snapshot_id=snapshot_id,
    )
    info = ConversationTypes.ConversationInfo(
        conversation_id,
        owner_id,
        product_id,
        snapshot_id,
        snapshot_id,
        uuid4(),
        original.created_at,
    )
    mocks = {
        "owned": AsyncMock(return_value=info),
        "participants": AsyncMock(
            return_value=(
                ConversationTypes.ConversationCharacterInfo(None, slot_id, 0),
            )
        ),
        "receipt": AsyncMock(return_value=None),
        "get": AsyncMock(return_value=original),
        "last": AsyncMock(return_value=original),
        "pending": AsyncMock(return_value=False),
        "create": AsyncMock(return_value=original),
        "replace": AsyncMock(return_value=updated),
        "delete": AsyncMock(return_value=2),
        "memory": AsyncMock(),
        "invalidate": AsyncMock(),
    }
    monkeypatch.setattr(Service, "get_owned_conversation", mocks["owned"])
    monkeypatch.setattr(Service, "list_conversation_characters", mocks["participants"])
    monkeypatch.setattr(Service, "invalidate_conversation_memories", mocks["memory"])
    for name, key in (
        ("get_message_request", "receipt"),
        ("get_message", "get"),
        ("get_last_message", "last"),
        ("has_pending_generation", "pending"),
        ("create_message", "create"),
        ("replace_message", "replace"),
        ("delete_messages_from", "delete"),
        ("invalidate_generation_history", "invalidate"),
    ):
        monkeypatch.setattr(Repository, name, mocks[key])
    return SimpleNamespace(
        owner_id=owner_id,
        conversation_id=conversation_id,
        snapshot_id=snapshot_id,
        slot_id=slot_id,
        info=info,
        original=original,
        updated=updated,
        mocks=mocks,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("character", [False, True])
async def test_fresh_create_locks_owner_and_preserves_sender_slot_and_digest(
    backend, character
):
    b = backend
    values = dict(
        conversation_id=b.conversation_id,
        user_id=b.owner_id,
        request_key="retry",
        content="안녕",
    )
    command = (
        types.CreateCharacterMessageCommand(**values, product_character_id=b.slot_id)
        if character
        else types.CreateMessageCommand(**values)
    )
    function = Service.create_character_message if character else Service.create_message
    async with AsyncSession() as session:
        result = await function(session, command)
        assert not session.in_transaction()
        b.mocks["owned"].assert_awaited_once_with(
            session,
            ConversationTypes.OwnedConversationCommand(
                conversation_id=b.conversation_id, user_id=b.owner_id, lock=True
            ),
        )
        b.mocks["create"].assert_awaited_once_with(
            session,
            command,
            b.snapshot_id,
            "character" if character else "user",
            None,
            b.slot_id if character else None,
            message_digest("안녕", b.slot_id if character else None, character),
        )
    assert result.id == b.original.id
    assert b.mocks["participants"].await_count == int(character)


@pytest.mark.asyncio
async def test_exact_retry_returns_original_before_pending_generation_check(backend):
    b = backend
    b.mocks["receipt"].return_value = MessageRequest(
        conversation_id=b.conversation_id,
        request_key="retry",
        input_digest=message_digest("Original"),
        message_id=b.original.id,
    )
    b.mocks["pending"].return_value = True
    async with AsyncSession() as session:
        result = await Service.create_message(
            session,
            types.CreateMessageCommand(
                conversation_id=b.conversation_id,
                user_id=b.owner_id,
                request_key="retry",
                content="Original",
            ),
        )
    assert result.id == b.original.id
    b.mocks["pending"].assert_not_awaited()
    b.mocks["create"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["different_input", "deleted", "replaced"])
async def test_retry_never_recreates_a_conflicting_or_tombstoned_message(
    backend, failure
):
    b = backend
    b.mocks["receipt"].return_value = MessageRequest(
        conversation_id=b.conversation_id,
        request_key="retry",
        input_digest=message_digest("Original"),
        message_id=None if failure == "deleted" else b.original.id,
    )
    if failure == "deleted":
        b.mocks["get"].return_value = None
    if failure == "replaced":
        b.original.revision = 2
    async with AsyncSession() as session:
        with pytest.raises(types.MessageConflictError):
            await Service.create_message(
                session,
                types.CreateMessageCommand(
                    conversation_id=b.conversation_id,
                    user_id=b.owner_id,
                    request_key="retry",
                    content="Different" if failure == "different_input" else "Original",
                ),
            )
        assert not session.in_transaction()
        if failure == "deleted":
            b.mocks["get"].assert_awaited_once_with(session, b.conversation_id, None)
    b.mocks["create"].assert_not_awaited()
    b.mocks["pending"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("character", [False, True])
async def test_replace_invalidates_memory_and_generation_history_before_same_id_write(
    backend, character
):
    b = backend
    events = []

    async def memory(*args):
        events.append("memory")

    async def invalidate(*args):
        events.append("generation_history")

    async def replace_message(*args):
        events.append("replace")
        return b.updated

    b.mocks["memory"].side_effect = memory
    b.mocks["invalidate"].side_effect = invalidate
    b.mocks["replace"].side_effect = replace_message
    values = dict(
        conversation_id=b.conversation_id,
        user_id=b.owner_id,
        message_id=b.original.id,
        expected_revision=1,
        content="Edited",
    )
    if character:
        b.original.sender_type = "character"
        b.original.product_character_id = b.slot_id
        command = types.ReplaceCharacterMessageCommand(
            **values, product_character_id=b.slot_id
        )
        function = Service.replace_character_message
    else:
        command = types.ReplaceMessageCommand(**values)
        function = Service.replace_message
    async with AsyncSession() as session:
        result = await function(session, command)
        assert not session.in_transaction()
        b.mocks["replace"].assert_awaited_once_with(session, b.original.id, "Edited")
        assert b.mocks["memory"].await_args.args[1].owner_id == b.owner_id
    assert (
        result.id == b.original.id
        and result.position == b.original.position
        and result.revision == 2
    )
    assert events == ["memory", "generation_history", "replace"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "error"),
    [
        ("missing", LookupError),
        ("sender", types.MessagePermissionError),
        ("pending", types.MessageConflictError),
        ("not_last", types.MessageConflictError),
        ("revision", types.MessageConflictError),
        ("character_version", ValueError),
    ],
)
async def test_replace_guards_prevent_invalidation_and_storage(backend, failure, error):
    b = backend
    if failure == "missing":
        b.mocks["get"].return_value = None
    elif failure == "sender":
        b.original.sender_type = "character"
    elif failure == "pending":
        b.mocks["pending"].return_value = True
    elif failure == "not_last":
        b.mocks["last"].return_value = message(b.conversation_id)
    elif failure == "revision":
        b.original.revision = 2
    else:
        b.original.sender_type = "character"
        b.original.product_character_id = b.slot_id
        b.original.product_snapshot_id = uuid4()
    values = dict(
        conversation_id=b.conversation_id,
        user_id=b.owner_id,
        message_id=b.original.id,
        expected_revision=1,
        content="Edited",
    )
    command = (
        types.ReplaceCharacterMessageCommand(**values, product_character_id=b.slot_id)
        if failure == "character_version"
        else types.ReplaceMessageCommand(**values)
    )
    function = (
        Service.replace_character_message
        if failure == "character_version"
        else Service.replace_message
    )
    async with AsyncSession() as session:
        with pytest.raises(error):
            await function(session, command)
        assert not session.in_transaction()
    b.mocks["memory"].assert_not_awaited()
    b.mocks["replace"].assert_not_awaited()


@pytest.mark.asyncio
async def test_rewind_invalidates_before_inclusive_position_delete_and_returns_count(
    backend,
):
    b = backend
    events = []

    async def memory(*args):
        events.append("memory")

    async def invalidate(*args):
        events.append("generation_history")

    async def delete(*args):
        events.append("delete")
        return 2

    b.mocks["memory"].side_effect = memory
    b.mocks["invalidate"].side_effect = invalidate
    b.mocks["delete"].side_effect = delete
    async with AsyncSession() as session:
        result = await Service.rewind_messages(
            session,
            types.RewindMessagesCommand(
                conversation_id=b.conversation_id,
                user_id=b.owner_id,
                message_id=b.original.id,
            ),
        )
        b.mocks["delete"].assert_awaited_once_with(
            session, b.conversation_id, b.original.position
        )
    assert result.deleted_count == 2 and events == [
        "memory",
        "generation_history",
        "delete",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["replace", "rewind"])
async def test_invalidation_failure_prevents_message_mutation_and_closes_transaction(
    backend, operation
):
    b = backend
    b.mocks["memory"].side_effect = RuntimeError("memory unavailable")
    common = dict(
        conversation_id=b.conversation_id, user_id=b.owner_id, message_id=b.original.id
    )
    command = (
        types.ReplaceMessageCommand(**common, expected_revision=1, content="Edited")
        if operation == "replace"
        else types.RewindMessagesCommand(**common)
    )
    async with AsyncSession() as session:
        with pytest.raises(RuntimeError, match="memory unavailable"):
            await (
                Service.replace_message
                if operation == "replace"
                else Service.rewind_messages
            )(session, command)
        assert not session.in_transaction()
    b.mocks["invalidate"].assert_not_awaited()
    b.mocks["replace"].assert_not_awaited()
    b.mocks["delete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_denial_happens_before_receipt_read(backend):
    b = backend
    b.mocks["owned"].side_effect = LookupError("Conversation not found.")
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await Service.create_message(
                session,
                types.CreateMessageCommand(
                    conversation_id=b.conversation_id,
                    user_id=b.owner_id,
                    request_key="retry",
                    content="Original",
                ),
            )
    b.mocks["receipt"].assert_not_awaited()
    b.mocks["create"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["blank", "request_key", "boolean_revision"])
async def test_invalid_input_is_rejected_before_conversation_lock(backend, failure):
    b = backend
    if failure == "boolean_revision":
        command = types.ReplaceMessageCommand(
            conversation_id=b.conversation_id,
            user_id=b.owner_id,
            message_id=b.original.id,
            expected_revision=True,
            content="Edited",
        )
        function = Service.replace_message
    else:
        command = types.CreateMessageCommand(
            conversation_id=b.conversation_id,
            user_id=b.owner_id,
            request_key="x" * 129 if failure == "request_key" else "retry",
            content=" " if failure == "blank" else "Original",
        )
        function = Service.create_message
    async with AsyncSession() as session:
        with pytest.raises(ValueError):
            await function(session, command)
        assert not session.in_transaction()
    b.mocks["owned"].assert_not_awaited()


@pytest.fixture
def chat_database(core_database):
    sync_session, session = core_database
    counter = [0]

    def next_position():
        counter[0] += 1
        return counter[0]

    connection = sync_session.connection().connection.driver_connection
    connection.create_function("next_position", 0, next_position)
    connection.execute("PRAGMA foreign_keys=ON")
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    metadata = MetaData()
    defaults = {
        "id": "(lower(hex(randomblob(16))))",
        "position": "(next_position())",
        "created_at": "CURRENT_TIMESTAMP",
        "updated_at": "CURRENT_TIMESTAMP",
        "revision": "1",
        "generated_by_ai": "false",
        "message_count": "0",
    }
    for model in (Message, MessageRequest, ProductGeneration, GenerationPrompt):
        columns = []
        for column in model.__table__.columns:
            column_type = (
                JSON()
                if isinstance(column.type, JSONB)
                else Uuid(native_uuid=False)
                if isinstance(column.type, Uuid)
                else column.type
            )
            constraints = (
                [ForeignKey("messages.id", ondelete="SET NULL")]
                if model is MessageRequest and column.name == "message_id"
                else []
            )
            columns.append(
                Column(
                    column.name,
                    column_type,
                    *constraints,
                    primary_key=column.primary_key,
                    server_default=text(defaults[column.name])
                    if column.name in defaults
                    else None,
                )
            )
        extra = (
            [UniqueConstraint("conversation_id", "position")]
            if model is Message
            else []
        )
        Table(model.__tablename__, metadata, *columns, *extra)
    metadata.create_all(sync_session.get_bind())
    yield sync_session, session


@pytest.mark.asyncio
async def test_sql_message_update_clears_provenance_and_rewind_preserves_tombstone(
    chat_database,
):
    sync_session, session = chat_database
    conversation_id, owner_id, other_id, snapshot_id = [uuid4() for _ in range(4)]

    def command(key):
        return types.CreateMessageCommand(
            conversation_id=conversation_id,
            user_id=owner_id,
            request_key=key,
            content=key,
        )

    first = await Repository.create_message(
        session, command("first"), snapshot_id, "user", None, None, "digest"
    )
    second = await Repository.create_message(
        session, command("second"), snapshot_id, "user", None, None, "second-digest"
    )
    other = await Repository.create_message(
        session,
        types.CreateMessageCommand(
            conversation_id=other_id,
            user_id=owner_id,
            request_key="other",
            content="Other",
        ),
        None,
        "user",
        None,
        None,
        "other-digest",
    )
    assert first.position < second.position < other.position
    assert await Repository.get_message(session, other_id, first.id) is None
    assert await Repository.get_message(session, conversation_id, None) is None
    sync_session.execute(
        update(Message)
        .where(Message.id == first.id)
        .values(
            content="SQL change",
            generation_id=uuid4(),
            model_id=uuid4(),
            generated_by_ai=True,
            token_count=8,
            emotion_tag="joy",
        )
        .execution_options(synchronize_session=False)
    )
    assert (
        await Repository.get_message(session, conversation_id, first.id)
    ).content == "SQL change"
    original_position = first.position
    changed = await Repository.replace_message(session, first.id, "Edited")
    assert (
        changed.id == first.id
        and changed.position == original_position
        and changed.revision == 2
    )
    assert (
        not changed.generated_by_ai
        and changed.generation_id
        is changed.model_id
        is changed.token_count
        is changed.emotion_tag
        is None
    )
    assert (
        await Repository.delete_messages_from(session, conversation_id, second.position)
        == 1
    )
    sync_session.expire_all()
    receipt = await Repository.get_message_request(session, conversation_id, "second")
    assert receipt.message_id is None and receipt.input_digest == "second-digest"
    assert await Repository.get_message(session, other_id, other.id) is not None
    assert (
        await Repository.delete_messages_from(session, conversation_id, second.position)
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("referenced_input", [False, True])
async def test_sql_generation_helpers_preserve_input_mode_metadata_lease_and_prompt(
    chat_database, referenced_input
):
    sync_session, session = chat_database
    conversation_id, owner_id, product_id, snapshot_id, model_id, slot_id = [
        uuid4() for _ in range(6)
    ]
    now = datetime(2026, 10, 28, tzinfo=UTC)
    info = ConversationTypes.ConversationInfo(
        conversation_id, owner_id, product_id, snapshot_id, snapshot_id, uuid4(), now
    )
    execution = ExecutionView(model_id, "provider", "model", "low", False, None)
    run = await Repository.create_generation(
        session,
        info,
        execution,
        owner_id,
        "generation",
        "digest",
        "Input",
        uuid4() if referenced_input else None,
    )
    assert sync_session.scalar(select(func.count()).select_from(Message)) == int(
        not referenced_input
    )
    assert await Repository.has_pending_generation(session, conversation_id)
    assert (
        await Repository.get_generation_by_request(session, uuid4(), "generation")
        is None
    )
    assert (
        await Repository.get_generation_by_request(session, owner_id, "generation")
        is run
    )
    metadata = {
        "version": 2,
        "phase": "result_ready",
        "extension": {"keep": [None, True, "raw"]},
    }
    await Repository.update_answer(
        session, run.id, metadata, now - timedelta(seconds=1)
    )
    assert [
        item.id for item in await Repository.list_expired_answers(session, now, 10)
    ] == [run.id]
    state = Mapper.generation_entity_to_state_info(run)
    await Repository.add_generation_message(
        session, state, types.GeneratedMessage(slot_id, "Output"), None
    )
    generated = sync_session.scalars(
        select(Message).where(Message.generated_by_ai.is_(True))
    ).one()
    assert (
        generated.generation_id == run.id
        and generated.model_id == model_id
        and generated.product_character_id == slot_id
    )
    await Repository.invalidate_generation_history(session, conversation_id, now)
    await Repository.invalidate_generation_history(
        session, conversation_id, now + timedelta(days=1)
    )
    terminal = await Repository.finish_generation(
        session, run.id, "succeeded", "result-digest", now, 1
    )
    assert (
        terminal.history_invalidated_at.replace(tzinfo=UTC) == now
        and terminal.message_count == 1
    )
    assert (
        terminal.answer_metadata == metadata
        and terminal.result_digest == "result-digest"
    )
    assert await Repository.list_expired_answers(session, now, 10) == []
    raw = '{"messages": [{"content": "원문"}]}'
    digest = hashlib.sha256(raw.encode()).hexdigest()
    await Repository.create_generation_prompt(
        session,
        run.id,
        request_json=raw,
        digest=digest,
        format_version=1,
        provider="provider",
        max_output_tokens=50,
    )
    prompt = await Repository.get_generation_prompt(session, run.id)
    assert (
        prompt.request_json,
        prompt.digest,
        prompt.format_version,
        prompt.provider,
        prompt.max_output_tokens,
    ) == (raw, digest, 1, "provider", 50)
