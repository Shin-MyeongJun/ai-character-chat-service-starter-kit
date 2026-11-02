"""Offline command/view contracts around trusted product and conversation values."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_conversation_query_contracts import snapshot_values

from app.db.models.chat import Conversation
from app.modules.chatting.conversation import types
from app.modules.chatting.conversation.service import command as StartService
from app.modules.chatting.conversation.service import views as ViewsService
from app.modules.chatting.conversation.service.command import context as ContextService
from app.modules.chatting.conversation.service.command import history as HistoryService
from app.modules.chatting.conversation.service.command import (
    versions as VersionsService,
)
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as ProductTypes
from app.modules.llm.types import ExecutionView


@pytest.fixture
def backend(monkeypatch):
    snapshot, runtime, source_id = snapshot_values()
    owner_id, conversation_id, start_id = uuid4(), uuid4(), uuid4()
    stamp = datetime(2026, 10, 28, tzinfo=UTC)
    runtime.composition.starts.append(
        ProductTypes.SnapshotStartInfo(start_id, source_id, "Start", "Pinned start", 0)
    )
    target = replace(snapshot, id=uuid4(), version=2)
    info = types.ConversationInfo(
        conversation_id,
        owner_id,
        snapshot.product_id,
        snapshot.id,
        snapshot.id,
        start_id,
        stamp,
        opening_mode="snapshot",
    )
    product = ProductTypes.ProductStateInfo(
        id=snapshot.product_id,
        title="Draft",
        description=None,
        opening_message=None,
        visibility="private",
        status="approved",
        created_at=stamp,
        updated_at=stamp,
        owner_id=owner_id,
        default_model_id=None,
        reasoning_effort=None,
        replacement_policy={},
        latest_snapshot_id=snapshot.id,
    )
    snapshots = {snapshot.id: snapshot, target.id: target}

    async def get_snapshot(session, command):
        return snapshots[command.snapshot_id]

    mocks = {
        "accessible": AsyncMock(return_value=product),
        "snapshot": AsyncMock(side_effect=get_snapshot),
        "available": AsyncMock(side_effect=get_snapshot),
        "runtime": AsyncMock(return_value=runtime),
        "owned": AsyncMock(return_value=info),
        "participants": AsyncMock(
            return_value=(
                types.ConversationCharacterInfo(
                    None, runtime.composition.characters[0].id, 0
                ),
            )
        ),
        "composition": AsyncMock(return_value=runtime.composition),
        "notes": AsyncMock(
            return_value=[
                (
                    target,
                    ProductTypes.ReleaseInfo(
                        target.id, 2, "Next", "Body", "media", "automatic"
                    ),
                )
            ]
        ),
        "create": AsyncMock(return_value=Conversation(**asdict(info))),
        "switch": AsyncMock(),
        "history": AsyncMock(
            return_value=Conversation(**asdict(replace(info, history_revision=2)))
        ),
        "dirty": AsyncMock(),
        "execution": AsyncMock(
            return_value=ExecutionView(uuid4(), "provider", "model", "low", False, None)
        ),
        "start": AsyncMock(
            return_value=types.ConversationStartView(
                snapshot.id,
                "snapshot",
                "Scene",
                types.RuntimeStart("Start", "Pinned start"),
                (),
                None,
            )
        ),
    }
    for name, mock in (
        ("get_accessible_product", "accessible"),
        ("get_product_snapshot", "snapshot"),
        ("ensure_snapshot_available", "available"),
        ("get_snapshot_composition", "composition"),
        ("list_product_releases", "notes"),
    ):
        monkeypatch.setattr(StartService.ProductQueryService, name, mocks[mock])
    monkeypatch.setattr(
        StartService.ProductViewsService, "get_snapshot_runtime", mocks["runtime"]
    )
    for module in (VersionsService, HistoryService, ContextService):
        monkeypatch.setattr(module, "get_owned_conversation", mocks["owned"])
    monkeypatch.setattr(
        ViewsService.QueryService, "get_owned_conversation", mocks["owned"]
    )
    monkeypatch.setattr(
        ViewsService.QueryService, "list_conversation_characters", mocks["participants"]
    )
    for name, mock in (
        ("create_conversation", "create"),
        ("switch_conversation_version", "switch"),
        ("advance_history_revision", "history"),
    ):
        monkeypatch.setattr(StartService.Repository, name, mocks[mock])
    monkeypatch.setattr(StartService, "mark_statistics_dirty", mocks["dirty"])
    monkeypatch.setattr(VersionsService, "mark_statistics_dirty", mocks["dirty"])
    monkeypatch.setattr(ContextService, "resolve_execution", mocks["execution"])
    monkeypatch.setattr(ContextService, "get_conversation_start", mocks["start"])
    return SimpleNamespace(
        snapshot=snapshot,
        target=target,
        snapshots=snapshots,
        runtime=runtime,
        owner_id=owner_id,
        info=info,
        mocks=mocks,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit", [False, True])
async def test_start_selects_published_option_uses_owner_lock_and_marks_statistics(
    backend, explicit
):
    b = backend
    async with AsyncSession() as session:
        result = await StartService.start_conversation(
            session,
            types.StartConversationCommand(
                product_id=b.info.product_id,
                user_id=b.owner_id,
                start_set_id=b.info.start_set_id if explicit else None,
            ),
        )
        assert not session.in_transaction()
    assert result == types.ConversationStartedInfo(
        b.info.id, b.snapshot.id, b.info.start_set_id
    )
    accessible = b.mocks["accessible"].await_args.args[1]
    assert accessible == ProductTypes.GetAccessibleProductCommand(
        product_id=b.info.product_id, user_id=b.owner_id, lock=True
    )
    created = b.mocks["create"].await_args.args[1]
    assert (
        created.snapshot_id == b.snapshot.id
        and created.start_set_id == b.info.start_set_id
    )
    assert created.title == "Pinned" and created.characters[0].character_id is None
    assert (
        created.characters[0].product_character_id
        == b.runtime.composition.characters[0].id
    )
    assert b.mocks["dirty"].await_args.args[
        1
    ] == ProductTypes.MarkStatisticsDirtyCommand(
        product_id=b.info.product_id, instant=b.info.created_at
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["unpublished", "no_options", "multiple", "wrong_option", "no_primary"]
)
async def test_start_rejects_invalid_publication_before_creation(backend, failure):
    b = backend
    start_id = None
    if failure == "unpublished":
        b.mocks["accessible"].return_value = replace(
            b.mocks["accessible"].return_value, latest_snapshot_id=None
        )
    elif failure == "no_options":
        b.runtime.composition.starts.clear()
    elif failure == "multiple":
        b.runtime.composition.starts.append(
            replace(b.runtime.composition.starts[0], id=uuid4())
        )
    elif failure == "wrong_option":
        start_id = uuid4()
    else:
        b.runtime.composition.characters[:] = [
            replace(b.runtime.composition.characters[0], is_primary=False)
        ]
    async with AsyncSession() as session:
        with pytest.raises(ValueError):
            await StartService.start_conversation(
                session,
                types.StartConversationCommand(
                    product_id=b.info.product_id,
                    user_id=b.owner_id,
                    start_set_id=start_id,
                ),
            )
        assert not session.in_transaction()
    b.mocks["create"].assert_not_awaited()
    b.mocks["dirty"].assert_not_awaited()


@pytest.mark.asyncio
async def test_same_version_switch_returns_before_snapshot_reads_and_writes(backend):
    b = backend
    async with AsyncSession() as session:
        result = await VersionsService.switch_version(
            session,
            types.SwitchVersionCommand(
                conversation_id=b.info.id,
                user_id=b.owner_id,
                target_snapshot_id=b.snapshot.id,
            ),
        )
        assert not session.in_transaction()
    assert result == types.VersionSwitchedInfo(b.snapshot.id, False)
    assert b.mocks["owned"].await_args.args[1].lock is True
    b.mocks["snapshot"].assert_not_awaited()
    b.mocks["switch"].assert_not_awaited()
    b.mocks["dirty"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [False, True])
async def test_forward_switch_passes_slots_mode_and_single_timestamp_to_storage(
    backend, automatic
):
    b = backend
    async with AsyncSession() as session:
        result = await VersionsService.switch_version(
            session,
            types.SwitchVersionCommand(
                conversation_id=b.info.id,
                user_id=b.owner_id,
                target_snapshot_id=b.target.id,
                automatic=automatic,
            ),
        )
        assert not session.in_transaction()
    assert result == types.VersionSwitchedInfo(b.target.id, True)
    args = b.mocks["switch"].await_args.args
    assert args[1:4] == (b.info.id, b.snapshot.id, b.target.id)
    assert args[4][0].product_character_id == b.runtime.composition.characters[0].id
    assert (
        args[5] == ("automatic" if automatic else "choice")
        and args[6].utcoffset() is not None
    )
    assert b.mocks["dirty"].await_args.args[1].instant == args[6]
    notes_command = b.mocks["notes"].await_args.args[1]
    assert notes_command.after_version == 1 and notes_command.through_version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "legacy",
        "other_product",
        "backward",
        "no_notes",
        "missing_note",
        "consent",
        "invalid_primary",
    ],
)
async def test_switch_policy_failures_do_not_rewrite_participants_or_queue_work(
    backend, failure
):
    b = backend
    if failure == "legacy":
        b.mocks["owned"].return_value = replace(b.info, product_snapshot_id=None)
    elif failure == "other_product":
        b.snapshots[b.target.id] = replace(b.target, product_id=uuid4())
    elif failure == "backward":
        b.snapshots[b.target.id] = replace(b.target, version=1)
    elif failure == "no_notes":
        b.mocks["notes"].return_value = []
    elif failure == "missing_note":
        b.mocks["notes"].return_value = [(b.target, None)]
    elif failure == "consent":
        b.mocks["notes"].return_value = [
            (
                b.target,
                replace(b.mocks["notes"].return_value[0][1], update_policy="choice"),
            )
        ]
    else:
        b.runtime.composition.characters[:] = [
            replace(b.runtime.composition.characters[0], is_primary=False)
        ]
    async with AsyncSession() as session:
        with pytest.raises((ValueError, LookupError)):
            await VersionsService.switch_version(
                session,
                types.SwitchVersionCommand(
                    conversation_id=b.info.id,
                    user_id=b.owner_id,
                    target_snapshot_id=b.target.id,
                    automatic=failure == "consent",
                ),
            )
        assert not session.in_transaction()
    b.mocks["switch"].assert_not_awaited()
    b.mocks["dirty"].assert_not_awaited()


@pytest.mark.asyncio
async def test_history_change_requires_owned_lock_and_returns_incremented_info(backend):
    b = backend
    async with AsyncSession() as session:
        info = await HistoryService.advance_history_revision(
            session,
            types.AdvanceHistoryRevisionCommand(
                conversation_id=b.info.id, user_id=b.owner_id
            ),
        )
        b.mocks["owned"].assert_awaited_once_with(
            session,
            types.OwnedConversationCommand(
                conversation_id=b.info.id, user_id=b.owner_id, lock=True
            ),
        )
        assert not session.in_transaction()
    assert (
        info.history_revision == 2
        and info.initial_snapshot_id == b.info.initial_snapshot_id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("participates", [False, True])
async def test_start_view_uses_initial_scene_and_current_primary_only_if_participating(
    backend, participates
):
    b = backend
    b.mocks["owned"].return_value = replace(b.info, product_snapshot_id=b.target.id)
    current_slot = uuid4()
    current = replace(
        b.runtime.composition,
        characters=[replace(b.runtime.composition.characters[0], id=current_slot)],
    )

    async def composition(session, command):
        return (
            b.runtime.composition if command.snapshot_id == b.snapshot.id else current
        )

    b.mocks["composition"].side_effect = composition
    b.mocks["participants"].return_value = (
        types.ConversationCharacterInfo(
            None, current_slot if participates else uuid4(), 0
        ),
    )
    async with AsyncSession() as session:
        result = await ViewsService.get_conversation_start(
            session,
            types.OwnedConversationCommand(
                conversation_id=b.info.id, user_id=b.owner_id
            ),
        )
    assert (
        result.initial_snapshot_id == b.snapshot.id
        and result.start.content == "Pinned start"
    )
    assert result.opening_message == "Scene"
    assert result.primary_product_character_id == (
        current_slot if participates else None
    )
    b.mocks["available"].assert_not_awaited()


def add_manual_lore(backend, second=False):
    b = backend
    books = list(b.runtime.composition.books)
    if second:
        books.append(replace(books[0], id=uuid4(), lorebook_snapshot_id=uuid4()))
        b.runtime.composition.books[:] = books
    for book in books:
        entry = {
            "id": str(uuid4()),
            "title": None,
            "content": "Pinned lore",
            "entry_type": "world",
            "activation_type": "manual",
            "is_enabled": True,
            "match_mode": "contains",
        }
        b.runtime.lorebooks[book.lorebook_snapshot_id] = (
            LorebookTypes.LorebookSnapshotInfo(
                book.lorebook_snapshot_id, None, 1, {"entries": [entry]}
            )
        )
    return tuple(
        book.snapshot_data["entries"][0]["id"] for book in b.runtime.lorebooks.values()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_manual_listing_uses_only_pinned_enabled_manual_entries(backend, legacy):
    b = backend
    ids = add_manual_lore(b)
    entries = next(iter(b.runtime.lorebooks.values())).snapshot_data["entries"]
    entries.extend(
        [
            {**entries[0], "id": "disabled", "is_enabled": False},
            {**entries[0], "id": "scene", "entry_type": "start_set"},
            {**entries[0], "id": "semantic", "activation_type": "semantic"},
        ]
    )
    if legacy:
        b.mocks["owned"].return_value = replace(b.info, product_snapshot_id=None)
    async with AsyncSession() as session:
        result = await ViewsService.list_manual_lore(
            session,
            types.OwnedConversationCommand(
                conversation_id=b.info.id, user_id=b.owner_id
            ),
        )
    assert result == (
        () if legacy else (types.ManualLoreInfo(ids[0], "이름 없는 로어"),)
    )
    if legacy:
        b.mocks["available"].assert_not_awaited()
        b.mocks["runtime"].assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_scopes_manual_ids_to_each_snapshot_and_keeps_initial_start(
    backend,
):
    b = backend
    ids = add_manual_lore(b, second=True)
    async with AsyncSession() as session:
        result = await ContextService.prepare_runtime_context(
            session,
            types.PrepareRuntimeContextCommand(
                conversation_id=b.info.id,
                user_id=b.owner_id,
                activation_text="supplied",
                activation_messages=(("user", "history"),),
                manual_entry_ids=ids,
            ),
        )
        assert not session.in_transaction()
    assert [entry["id"] for book in result.lorebooks for entry in book.entries] == list(
        ids
    )
    assert result.start.content == "Pinned start" and result.opening_message == "Scene"
    assert "opening_message" not in result.settings
    result.lorebooks[0].entries[0]["content"] = "consumer edit"
    assert (
        next(iter(b.runtime.lorebooks.values())).snapshot_data["entries"][0]["content"]
        == "Pinned lore"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["legacy", "unknown_manual", "scene_manual"])
async def test_invalid_runtime_mapping_or_manual_id_does_not_return_a_context(
    backend, failure
):
    b = backend
    ids = add_manual_lore(b)
    if failure == "legacy":
        b.mocks["owned"].return_value = replace(b.info, product_snapshot_id=None)
        manual = ()
    elif failure == "unknown_manual":
        manual = (str(uuid4()),)
    else:
        next(iter(b.runtime.lorebooks.values())).snapshot_data["entries"][0][
            "entry_type"
        ] = "start_set"
        manual = ids
    async with AsyncSession() as session:
        with pytest.raises(ValueError):
            await ContextService.prepare_runtime_context(
                session,
                types.PrepareRuntimeContextCommand(
                    conversation_id=b.info.id,
                    user_id=b.owner_id,
                    manual_entry_ids=manual,
                ),
            )
        assert not session.in_transaction()
    b.mocks["start"].assert_not_awaited()
    if failure == "legacy":
        b.mocks["execution"].assert_not_awaited()
