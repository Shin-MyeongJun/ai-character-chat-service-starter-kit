"""Offline replacement selection, announcement deadlines and advisory parity."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import types as ProductTypes
from app.modules.llm import types as Types
from app.modules.llm.service.command import replacement as Command
from app.modules.llm.service.util.replacement_policy import choose_replacement
from app.modules.llm.service.views import replacement as Views

DEADLINE = datetime(2026, 10, 28, tzinfo=UTC)


@dataclass
class Routing:
    snapshot: ProductTypes.ProductSnapshotInfo
    original: Types.ModelInfo
    target: Types.ModelInfo
    model: AsyncMock
    candidates: AsyncMock
    history: AsyncMock
    create: AsyncMock
    admin: AsyncMock
    retire: AsyncMock
    snapshot_lookup: AsyncMock
    provider: AsyncMock


@pytest.fixture
def routing(monkeypatch: pytest.MonkeyPatch) -> Routing:
    original = Types.ModelInfo(
        id=UUID(int=1),
        provider_id=UUID(int=10),
        model_name="original",
        is_enabled=True,
        capabilities={"model_family": "family", "reasoning_efforts": ["medium"]},
        retirement_announced_at=DEADLINE - timedelta(days=1),
        shutdown_at=DEADLINE + timedelta(days=1),
    )
    target = replace(
        original,
        id=UUID(int=2),
        model_name="replacement",
        capabilities={"model_family": "family", "reasoning_efforts": ["high", "low"]},
        retirement_announced_at=None,
        shutdown_at=None,
    )
    snapshot = ProductTypes.ProductSnapshotInfo(
        id=UUID(int=100),
        product_id=UUID(int=101),
        version=1,
        snapshot_data={
            "title": "Work",
            "model": {"id": str(original.id), "reasoning_effort": "medium"},
            "replacement_policy": {"scope": "same_provider", "unavailable": "pause"},
        },
        expires_at=None,
        expiry_reason=None,
    )
    item = Routing(
        snapshot=snapshot,
        original=original,
        target=target,
        model=AsyncMock(return_value=original),
        candidates=AsyncMock(return_value=[target]),
        history=AsyncMock(return_value=None),
        create=AsyncMock(),
        admin=AsyncMock(),
        retire=AsyncMock(return_value=None),
        snapshot_lookup=AsyncMock(return_value=snapshot),
        provider=AsyncMock(
            return_value=Types.ProviderInfo(original.provider_id, "openai", True)
        ),
    )
    monkeypatch.setattr(
        Command.ProductQueryService,
        "get_product_snapshot",
        item.snapshot_lookup,
    )
    monkeypatch.setattr(Command.QueryService, "get_model", item.model)
    monkeypatch.setattr(
        Command.QueryService,
        "get_provider",
        item.provider,
    )
    monkeypatch.setattr(Command.QueryService, "list_candidate_models", item.candidates)
    monkeypatch.setattr(Command.Repository, "get_model_replacement", item.history)
    monkeypatch.setattr(Command.Repository, "create_model_replacement", item.create)
    monkeypatch.setattr(Command.IdentityQueryService, "require_admin", item.admin)
    monkeypatch.setattr(Command.Repository, "set_model_retirement", item.retire)
    return item


@pytest.mark.asyncio
@pytest.mark.parametrize("future_notice", [False, True])
async def test_normal_execution_never_locks_snapshot_or_accesses_replacement_history(
    routing: Routing, future_notice: bool
) -> None:
    item = routing
    item.model.return_value = replace(
        item.original,
        retirement_announced_at=DEADLINE + timedelta(seconds=1)
        if future_notice
        else None,
    )
    async with AsyncSession() as session:
        execution = await Command.resolve_execution(
            session,
            Types.ResolveExecutionCommand(snapshot_id=item.snapshot.id, now=DEADLINE),
        )
        item.snapshot_lookup.assert_awaited_once_with(
            session,
            ProductTypes.ProductSnapshotCommand(
                snapshot_id=item.snapshot.id, lock=False
            ),
        )
        item.model.assert_awaited_once_with(
            session, Types.GetModelCommand(model_id=item.original.id, refresh=True)
        )
    assert execution.model_id == item.original.id
    assert not execution.replacement and execution.scheduled_at is None
    item.candidates.assert_not_awaited()
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_withdrawn_notice_is_rechecked_after_lock_before_any_history_write(
    routing: Routing,
) -> None:
    item = routing
    item.model.side_effect = [
        item.original,
        replace(item.original, retirement_announced_at=None),
    ]
    item.provider.side_effect = [
        Types.ProviderInfo(item.original.provider_id, "before", True),
        Types.ProviderInfo(item.original.provider_id, "after", True),
    ]
    async with AsyncSession() as session:
        execution = await Command.resolve_execution(
            session,
            Types.ResolveExecutionCommand(snapshot_id=item.snapshot.id, now=DEADLINE),
        )
        assert item.snapshot_lookup.await_args_list == [
            call(
                session,
                ProductTypes.ProductSnapshotCommand(
                    snapshot_id=item.snapshot.id, lock=lock
                ),
            )
            for lock in (False, True)
        ]
    assert execution.model_id == item.original.id and execution.provider == "after"
    assert not execution.replacement and execution.scheduled_at is None
    item.candidates.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_is_reread_under_lock_instead_of_writing_stale_plan(
    routing: Routing,
) -> None:
    item = routing
    locked_snapshot = replace(
        item.snapshot,
        snapshot_data={
            **item.snapshot.snapshot_data,
            "replacement_policy": {
                "scope": "allowlist",
                "model_ids": [],
                "unavailable": "pause",
            },
        },
    )
    item.snapshot_lookup.side_effect = [item.snapshot, locked_snapshot]
    async with AsyncSession() as session:
        with pytest.raises(ValueError, match="No permitted replacement"):
            await Command.resolve_execution(
                session,
                Types.ResolveExecutionCommand(
                    snapshot_id=item.snapshot.id, now=DEADLINE
                ),
            )
        item.candidates.assert_awaited_once_with(
            session, Types.ListCandidateModelsCommand(refresh=True)
        )
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["snapshot", "model", "provider"])
async def test_disappeared_locked_state_keeps_errors_and_does_not_write_history(
    routing: Routing, missing: str
) -> None:
    item = routing
    if missing == "snapshot":
        item.snapshot_lookup.side_effect = [
            item.snapshot,
            LookupError("Version not found."),
        ]
        expected_error: type[Exception] = LookupError
        message = "Version not found"
    elif missing == "model":
        item.model.side_effect = [item.original, None]
        expected_error = ValueError
        message = "Configured model is missing"
    else:
        item.provider.side_effect = [
            Types.ProviderInfo(item.original.provider_id, "openai", True),
            None,
        ]
        expected_error = ValueError
        message = "Configured provider is missing"
    async with AsyncSession() as session:
        with pytest.raises(expected_error, match=message):
            await Command.resolve_execution(
                session,
                Types.ResolveExecutionCommand(
                    snapshot_id=item.snapshot.id, now=DEADLINE
                ),
            )
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_now", [False, True])
async def test_lock_wait_rechecks_clock_but_preserves_explicit_evaluation_time(
    routing: Routing, monkeypatch: pytest.MonkeyPatch, explicit_now: bool
) -> None:
    item = routing
    before, after = DEADLINE - timedelta(seconds=1), DEADLINE + timedelta(seconds=1)
    clock = Mock(wraps=datetime)
    clock.now.side_effect = [before, after]
    monkeypatch.setattr(Command, "datetime", clock)
    async with AsyncSession() as session:
        execution = await Command.resolve_execution(
            session,
            Types.ResolveExecutionCommand(
                snapshot_id=item.snapshot.id, now=before if explicit_now else None
            ),
        )
    assert execution.model_id == (item.original.id if explicit_now else item.target.id)
    assert execution.replacement is not explicit_now
    assert execution.scheduled_at == (DEADLINE if explicit_now else after)
    assert clock.now.call_count == (0 if explicit_now else 2)
    assert item.create.await_count == 1


@pytest.mark.asyncio
async def test_version_expired_while_waiting_for_lock_cannot_create_replacement(
    routing: Routing,
) -> None:
    item = routing
    item.snapshot_lookup.side_effect = [
        item.snapshot,
        replace(item.snapshot, expires_at=DEADLINE, expiry_reason="withdrawn"),
    ]
    async with AsyncSession() as session:
        with pytest.raises(
            ValueError, match="Version expired. History and memories are preserved"
        ):
            await Command.resolve_execution(
                session,
                Types.ResolveExecutionCommand(
                    snapshot_id=item.snapshot.id, now=DEADLINE
                ),
            )
    assert item.snapshot_lookup.await_count == 2
    item.candidates.assert_not_awaited()
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_during_lock_wait_never_falls_back_to_original(
    routing: Routing, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = routing
    item.snapshot.snapshot_data["replacement_policy"] = {
        "scope": "same_provider",
        "unavailable": "use_original_until_shutdown",
    }
    item.candidates.return_value = []
    clock = Mock(wraps=datetime)
    clock.now.side_effect = [DEADLINE - timedelta(seconds=1), item.original.shutdown_at]
    monkeypatch.setattr(Command, "datetime", clock)
    async with AsyncSession() as session:
        with pytest.raises(ValueError, match="No permitted replacement"):
            await Command.resolve_execution(
                session, Types.ResolveExecutionCommand(snapshot_id=item.snapshot.id)
            )
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, 0, 86400])
async def test_notice_is_read_only_and_agrees_with_plan_and_switch_boundary(
    routing: Routing, offset: int
) -> None:
    item = routing
    now = DEADLINE + timedelta(seconds=offset)
    async with AsyncSession() as session:
        notice = await Views.execution_notice(
            session, Types.ExecutionNoticeCommand(snapshot=item.snapshot, now=now)
        )
        item.history.assert_not_awaited()
        item.create.assert_not_awaited()
        assert notice is not None
        assert notice.state == ("scheduled" if offset < 0 else "replacement_ready")
        assert notice.replacement_model_id == item.target.id
        assert notice.replacement_reasoning_effort == "low"
        execution = await Command.resolve_execution(
            session,
            Types.ResolveExecutionCommand(snapshot_id=item.snapshot.id, now=now),
        )
    assert execution.model_id == (item.original.id if offset < 0 else item.target.id)
    assert execution.replacement is (offset >= 0)
    assert execution.scheduled_at == max(now, DEADLINE)
    assert item.create.await_count == 1
    assert item.create.await_args is not None
    assert item.create.await_args.args[1:] == (
        item.snapshot.id,
        item.original.id,
        item.target.id,
        "low",
        max(now, DEADLINE),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offset,policy,continues",
    [
        (-1, "pause", True),
        (0, "pause", False),
        (0, "use_original_until_shutdown", True),
        (86400, "use_original_until_shutdown", False),
    ],
)
async def test_unavailable_policy_stops_at_deadline_or_shutdown_without_history_write(
    routing: Routing, offset: int, policy: str, continues: bool
) -> None:
    item = routing
    item.candidates.return_value = []
    item.snapshot.snapshot_data["replacement_policy"] = {
        "scope": "same_provider",
        "unavailable": policy,
    }
    now = DEADLINE + timedelta(seconds=offset)
    async with AsyncSession() as session:
        notice = await Views.execution_notice(
            session, Types.ExecutionNoticeCommand(snapshot=item.snapshot, now=now)
        )
        assert notice is not None
        assert notice.state == ("replacement_unavailable" if continues else "paused")
        command = Types.ResolveExecutionCommand(snapshot_id=item.snapshot.id, now=now)
        if continues:
            execution = await Command.resolve_execution(session, command)
            assert execution.model_id == item.original.id
            assert execution.replacement_unavailable is True
        else:
            with pytest.raises(ValueError, match="No permitted replacement"):
                await Command.resolve_execution(session, command)
    item.history.assert_not_awaited()
    item.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_target_history_prevents_duplicate_insert_but_does_not_pin_choice(
    routing: Routing,
) -> None:
    item = routing
    item.history.return_value = object()  # The real mapper consumes existence only.
    async with AsyncSession() as session:
        command = Types.ResolveExecutionCommand(
            snapshot_id=item.snapshot.id, now=DEADLINE
        )
        first = await Command.resolve_execution(session, command)
        item.create.assert_not_awaited()
        next_target = replace(item.target, id=UUID(int=3), model_name="new-choice")
        item.candidates.return_value = [next_target]
        item.history.return_value = None
        second = await Command.resolve_execution(session, command)
    assert (first.model_id, second.model_id) == (item.target.id, next_target.id)
    assert item.create.await_count == 1
    assert item.history.await_args is not None
    assert item.history.await_args.args[1:] == (
        item.snapshot.id,
        item.original.id,
        next_target.id,
    )


def test_selector_filters_shutdown_disabled_and_unsupported_candidates_before_uuid_tie(
    routing: Routing,
) -> None:
    item = routing
    winner = replace(item.target, id=UUID(int=3))
    choices = [
        item.original,
        replace(item.target, id=UUID(int=4)),
        replace(item.target, id=UUID(int=2), shutdown_at=DEADLINE),
        replace(item.target, id=UUID(int=0), is_enabled=False),
        replace(
            item.target, id=UUID(int=5), capabilities={"reasoning_efforts": ["unknown"]}
        ),
        winner,
    ]
    assert choose_replacement(
        item.original, choices, {"scope": "same_provider"}, "medium", now=DEADLINE
    ) == (winner, "low")
    assert (
        choose_replacement(
            item.original,
            choices,
            {"scope": "allowlist", "model_ids": []},
            "medium",
            now=DEADLINE,
        )
        is None
    )


@pytest.mark.asyncio
async def test_retirement_checks_admin_before_write_and_keeps_not_found_contract(
    routing: Routing,
) -> None:
    item = routing
    command = Types.AnnounceRetirementCommand(
        actor_id=UUID(int=99),
        model_id=item.original.id,
        announced_at=DEADLINE,
        shutdown_at=DEADLINE + timedelta(days=1),
    )
    async with AsyncSession() as session:
        item.admin.side_effect = LookupError("admin required")
        with pytest.raises(LookupError, match="admin required"):
            await Command.announce_retirement(session, command)
        item.retire.assert_not_awaited()
        item.admin.side_effect = None
        with pytest.raises(LookupError, match="Model not found"):
            await Command.announce_retirement(session, command)
    assert item.retire.await_count == 1
