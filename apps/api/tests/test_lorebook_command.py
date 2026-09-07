from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.models.lorebook import Lorebook, LorebookEntry
from app.modules.lorebook import constraints, repository, types
from app.modules.lorebook.service import command as service
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session():
    async with AsyncSession() as value:
        yield value


@pytest.fixture
def transaction_events(session):
    events = []
    event.listen(
        session.sync_session, "after_commit", lambda _: events.append("commit")
    )
    event.listen(
        session.sync_session, "after_rollback", lambda _: events.append("rollback")
    )
    return events


@pytest.fixture
def lorebook():
    now = datetime.now(UTC)
    return Lorebook(
        id=uuid4(),
        owner_id=uuid4(),
        title="Original lorebook",
        description="Original description",
        visibility="private",
        status="approved",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def entry(lorebook):
    now = datetime.now(UTC)
    return LorebookEntry(
        id=uuid4(),
        lorebook_id=lorebook.id,
        title="Original entry",
        content="Original content",
        entry_type="world",
        activation_type="keyword",
        key_triggers=["moon"],
        match_mode="contains",
        priority=10,
        token_budget=120,
        placement="before_history",
        is_enabled=True,
        metadata_={"source": "fixture"},
        embedding=[0.25, 0.5],
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def commands(lorebook, entry):
    owner = {"lorebook_id": lorebook.id, "owner_id": lorebook.owner_id}
    return SimpleNamespace(
        create=types.LorebookCreate(
            owner_id=lorebook.owner_id,
            title="New lorebook",
            description="New description",
        ),
        update=types.LorebookUpdate(
            **owner,
            title="Updated lorebook",
            description=None,
            visibility="public",
        ),
        status=types.LorebookStatusChange(**owner, status="rejected"),
        delete=types.LorebookDelete(**owner),
        create_entry=types.LorebookEntryCreate(
            **owner,
            title="New entry",
            content="New content",
            entry_type="term",
            activation_type="keyword",
            key_triggers=["moon", "luna"],
            match_mode="contains",
            priority=20,
            token_budget=80,
            placement="after_memory",
            metadata={"source": "command"},
        ),
        update_entry=types.LorebookEntryUpdate(
            **owner,
            entry_id=entry.id,
            title=None,
            content="Updated content",
            entry_type="rule",
            activation_type="always",
            key_triggers=None,
            match_mode="exact",
            priority=-5,
            token_budget=None,
            placement="system_top",
            is_enabled=False,
            metadata=None,
        ),
        delete_entry=types.LorebookEntryDelete(
            **owner,
            entry_id=entry.id,
        ),
    )


@pytest.fixture
def repo(monkeypatch, lorebook, entry):
    mocks = SimpleNamespace()
    names = (
        "create_lorebook",
        "get_lorebook_by_id_and_owner_id",
        "update_lorebook",
        "delete_lorebook",
        "create_lorebook_entry",
        "get_lorebook_entry",
        "update_lorebook_entry",
        "delete_lorebook_entry",
    )
    for name in names:
        mock = AsyncMock()
        monkeypatch.setattr(repository, name, mock)
        setattr(mocks, name, mock)
    mocks.get_lorebook_by_id_and_owner_id.return_value = lorebook
    mocks.update_lorebook.return_value = lorebook
    mocks.get_lorebook_entry.return_value = entry
    mocks.update_lorebook_entry.return_value = entry
    return mocks


async def test_create_returns_result_with_db_defaults_after_commit(
    session, transaction_events, commands, repo
):
    async def persist(db_session, entity):
        assert db_session.in_transaction()
        entity.id = uuid4()
        entity.created_at = entity.updated_at = datetime.now(UTC)
        return entity

    repo.create_lorebook.side_effect = persist

    result = await service.create_lorebook(session, commands.create)

    assert isinstance(result, types.LorebookInfo)
    assert result.owner_id == commands.create.owner_id
    assert result.title == commands.create.title
    assert result.status == "draft"
    assert result.visibility == "private"
    assert result.created_at is not None
    assert transaction_events == ["commit"]
    assert not session.in_transaction()


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " \t"),
        ("title", "x" * (constraints.LOREBOOK_TITLE_MAX_LENGTH + 1)),
        (
            "description",
            "x" * (constraints.LOREBOOK_DESCRIPTION_MAX_LENGTH + 1),
        ),
        ("visibility", "unknown"),
    ],
)
async def test_invalid_profile_rolls_back_without_repository_write(
    session, transaction_events, commands, repo, operation, field, value
):
    invalid_command = replace(getattr(commands, operation), **{field: value})
    function = getattr(service, f"{operation}_lorebook")

    with pytest.raises(ValueError):
        await function(session, invalid_command)

    repo.create_lorebook.assert_not_awaited()
    repo.update_lorebook.assert_not_awaited()
    assert transaction_events == ["rollback"]
    assert not session.in_transaction()


async def test_update_preserves_identity_and_status_and_clears_description(
    session, transaction_events, lorebook, commands, repo
):
    result = await service.update_lorebook(session, commands.update)

    assert result.id == commands.update.lorebook_id
    assert result.owner_id == commands.update.owner_id
    assert result.status == "approved"
    assert result.title == commands.update.title
    assert result.visibility == "public"
    assert result.description is None
    repo.get_lorebook_by_id_and_owner_id.assert_awaited_once_with(
        session, lorebook.id, lorebook.owner_id, for_update=True
    )
    assert transaction_events == ["commit"]


@pytest.mark.parametrize(
    ("function_name", "command_name", "mutation"),
    [
        ("update_lorebook", "update", "update_lorebook"),
        ("change_lorebook_status", "status", "update_lorebook"),
        ("delete_lorebook", "delete", "delete_lorebook"),
        ("create_lorebook_entry", "create_entry", "create_lorebook_entry"),
        ("update_lorebook_entry", "update_entry", "update_lorebook_entry"),
        ("delete_lorebook_entry", "delete_entry", "delete_lorebook_entry"),
    ],
)
async def test_missing_or_non_owned_lorebook_prevents_mutation(
    session, transaction_events, commands, repo, function_name, command_name, mutation
):
    repo.get_lorebook_by_id_and_owner_id.return_value = None
    command = getattr(commands, command_name)

    with pytest.raises(LookupError, match="Lorebook not found"):
        await getattr(service, function_name)(session, command)

    repo.get_lorebook_by_id_and_owner_id.assert_awaited_once_with(
        session, command.lorebook_id, command.owner_id, for_update=True
    )
    getattr(repo, mutation).assert_not_awaited()
    if "entry" in command_name:
        repo.get_lorebook_entry.assert_not_awaited()
    assert transaction_events == ["rollback"]


async def test_status_change_leaves_profile_unchanged(
    session, transaction_events, lorebook, commands, repo
):
    original_title = lorebook.title
    original_visibility = lorebook.visibility

    result = await service.change_lorebook_status(session, commands.status)

    assert result.status == "rejected"
    assert result.title == original_title
    assert result.visibility == original_visibility
    assert transaction_events == ["commit"]


@pytest.mark.parametrize("operation", ["create", "status"])
async def test_invalid_status_is_rejected_before_write(
    session, transaction_events, commands, repo, operation
):
    invalid_command = replace(getattr(commands, operation), status="unknown")
    function = (
        service.create_lorebook
        if operation == "create"
        else service.change_lorebook_status
    )

    with pytest.raises(ValueError):
        await function(session, invalid_command)

    repo.create_lorebook.assert_not_awaited()
    repo.update_lorebook.assert_not_awaited()
    assert transaction_events == ["rollback"]


async def test_delete_commits_after_owner_check(
    session, transaction_events, lorebook, commands, repo
):
    result = await service.delete_lorebook(session, commands.delete)

    assert result is None
    repo.delete_lorebook.assert_awaited_once_with(session, lorebook)
    assert transaction_events == ["commit"]


async def test_create_entry_returns_result_after_owned_parent_check(
    session, transaction_events, lorebook, commands, repo
):
    async def persist(db_session, entity):
        assert db_session.in_transaction()
        entity.id = uuid4()
        entity.created_at = entity.updated_at = datetime.now(UTC)
        return entity

    repo.create_lorebook_entry.side_effect = persist

    result = await service.create_lorebook_entry(session, commands.create_entry)

    assert isinstance(result, types.LorebookEntryInfo)
    assert result.lorebook_id == lorebook.id
    assert result.title == commands.create_entry.title
    assert result.key_triggers == commands.create_entry.key_triggers
    assert result.metadata == commands.create_entry.metadata
    repo.get_lorebook_by_id_and_owner_id.assert_awaited_once_with(
        session, lorebook.id, lorebook.owner_id, for_update=True
    )
    assert transaction_events == ["commit"]


@pytest.mark.parametrize("operation", ["create_entry", "update_entry"])
@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"content": "\n "}, id="blank-content"),
        pytest.param({"title": "\t"}, id="blank-title"),
        pytest.param({"entry_type": "unknown"}, id="entry-type"),
        pytest.param({"activation_type": "unknown"}, id="activation-type"),
        pytest.param({"match_mode": "unknown"}, id="match-mode"),
        pytest.param({"placement": "unknown"}, id="placement"),
        pytest.param({"token_budget": -1}, id="negative-token-budget"),
        pytest.param(
            {
                "activation_type": "keyword",
                "key_triggers": [],
                "is_enabled": True,
            },
            id="keyword-without-trigger",
        ),
        pytest.param(
            {"priority": constraints.POSTGRES_INTEGER_MAX + 1},
            id="priority-overflow",
        ),
        pytest.param(
            {"token_budget": constraints.POSTGRES_INTEGER_MAX + 1},
            id="token-budget-overflow",
        ),
        pytest.param(
            {"content": "x" * (constraints.ENTRY_CONTENT_MAX_LENGTH + 1)},
            id="content-too-long",
        ),
        pytest.param(
            {"key_triggers": ["x" * (constraints.ENTRY_TRIGGER_MAX_LENGTH + 1)]},
            id="trigger-too-long",
        ),
        pytest.param({"key_triggers": ["moon", " "]}, id="blank-trigger"),
        pytest.param(
            {"match_mode": "regex", "key_triggers": ["["]},
            id="invalid-regex",
        ),
        pytest.param({"metadata": {"bad": object()}}, id="non-json-metadata"),
        pytest.param(
            {"metadata": {"large": "x" * constraints.ENTRY_METADATA_MAX_BYTES}},
            id="metadata-too-large",
        ),
    ],
)
async def test_invalid_entry_rolls_back_before_parent_lookup_or_write(
    session, transaction_events, commands, repo, operation, changes
):
    invalid_command = replace(getattr(commands, operation), **changes)
    function = {
        "create_entry": service.create_lorebook_entry,
        "update_entry": service.update_lorebook_entry,
    }[operation]

    with pytest.raises(ValueError):
        await function(session, invalid_command)

    repo.get_lorebook_by_id_and_owner_id.assert_not_awaited()
    repo.get_lorebook_entry.assert_not_awaited()
    repo.create_lorebook_entry.assert_not_awaited()
    repo.update_lorebook_entry.assert_not_awaited()
    assert transaction_events == ["rollback"]
    assert not session.in_transaction()


async def test_update_entry_clears_optional_fields_without_changing_scope(
    session, transaction_events, lorebook, entry, commands, repo
):
    original_embedding = entry.embedding

    result = await service.update_lorebook_entry(session, commands.update_entry)

    assert result.id == entry.id
    assert result.lorebook_id == lorebook.id
    assert result.title is None
    assert result.key_triggers is None
    assert result.token_budget is None
    assert result.metadata == {}
    assert result.content == commands.update_entry.content
    assert not result.is_enabled
    assert entry.embedding is original_embedding
    repo.get_lorebook_entry.assert_awaited_once_with(
        session,
        commands.update_entry.entry_id,
        commands.update_entry.lorebook_id,
        for_update=True,
    )
    repo.update_lorebook_entry.assert_awaited_once_with(session, entry)
    assert transaction_events == ["commit"]


@pytest.mark.parametrize(
    ("operation", "mutation"),
    [
        ("update_entry", "update_lorebook_entry"),
        ("delete_entry", "delete_lorebook_entry"),
    ],
)
async def test_entry_mutation_does_not_cross_lorebook_boundary(
    session, transaction_events, lorebook, entry, commands, repo, operation, mutation
):
    command = getattr(commands, operation)
    entry.lorebook_id = uuid4()

    async def parent_scoped_lookup(
        db_session, entry_id, lorebook_id, *, for_update=False
    ):
        assert db_session is session
        assert for_update
        if entry.id == entry_id and entry.lorebook_id == lorebook_id:
            return entry
        return None

    repo.get_lorebook_entry.side_effect = parent_scoped_lookup

    with pytest.raises(LookupError, match="Lorebook entry not found"):
        function = {
            "update_entry": service.update_lorebook_entry,
            "delete_entry": service.delete_lorebook_entry,
        }[operation]
        await function(session, command)

    repo.get_lorebook_by_id_and_owner_id.assert_awaited_once_with(
        session, lorebook.id, lorebook.owner_id, for_update=True
    )
    repo.get_lorebook_entry.assert_awaited_once_with(
        session, command.entry_id, command.lorebook_id, for_update=True
    )
    getattr(repo, mutation).assert_not_awaited()
    assert transaction_events == ["rollback"]


async def test_delete_entry_commits_after_parent_and_entry_scope_checks(
    session, transaction_events, entry, commands, repo
):
    result = await service.delete_lorebook_entry(session, commands.delete_entry)

    assert result is None
    repo.get_lorebook_entry.assert_awaited_once_with(
        session,
        commands.delete_entry.entry_id,
        commands.delete_entry.lorebook_id,
        for_update=True,
    )
    repo.delete_lorebook_entry.assert_awaited_once_with(session, entry)
    assert transaction_events == ["commit"]


async def test_repository_failure_propagates_and_rolls_back(
    session, transaction_events, commands, repo
):
    failure = IntegrityError(
        "UPDATE lorebook_entries", {}, RuntimeError("constraint failed")
    )
    repo.update_lorebook_entry.side_effect = failure

    with pytest.raises(IntegrityError) as caught:
        await service.update_lorebook_entry(session, commands.update_entry)

    assert caught.value is failure
    assert transaction_events == ["rollback"]
    assert not session.in_transaction()


async def test_existing_transaction_is_not_committed_by_service(
    session, transaction_events, commands, repo
):
    async with session.begin():
        with pytest.raises(InvalidRequestError):
            await service.create_lorebook(session, commands.create)
        repo.create_lorebook.assert_not_awaited()
        assert transaction_events == []
        assert session.in_transaction()
