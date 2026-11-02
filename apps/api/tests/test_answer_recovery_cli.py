"""Operations CLI defaults to read only and emits no prompt or investigation text."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from test_generation_completion_contracts import Backend
from test_generation_completion_contracts import backend as backend

from app import answer_recovery as Cli
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.service.command import answer_recovery as Recovery


@pytest.mark.asyncio
async def test_inspect_is_read_only_and_manual_cli_records_one_attempt(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    item = backend
    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setenv("DATABASE_URL", "unused-test-url")
    monkeypatch.setattr(Cli, "create_async_engine", lambda url: engine)
    monkeypatch.setattr(
        Cli, "async_sessionmaker", lambda *args, **kwargs: item.sessions
    )
    assert await Cli.run_recovery(item.generation_id, item.owner_id) == 0
    assert item.state().answer_recovery_attempts == 0
    assert not any(
        sql.startswith(("INSERT", "UPDATE", "DELETE")) for sql in item.executed
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["attempt_count"] == 0 and inspected["attempts"] == []
    item.change(answer_recovery_quarantined_at=datetime.now(UTC))
    assert (
        await Cli.run_recovery(
            item.generation_id,
            item.owner_id,
            retry=True,
            operator="ops",
            reason="PRIVATE investigation",
        )
        == 0
    )
    result = capsys.readouterr().out
    assert (
        "Output" not in result
        and "PRIVATE" not in result
        and "execution_token" not in result
    )
    assert (
        item.state().answer_recovery_attempts == 1
        and item.state().status == "succeeded"
    )
    assert await Cli.run_recovery(item.generation_id, item.owner_id) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["attempts"][0]["manual"] is True
    assert engine.dispose.await_count == 3


@pytest.mark.asyncio
async def test_inspection_denies_wrong_owner_without_returning_history(
    backend: Backend,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = MagicMock(dispose=AsyncMock())
    monkeypatch.setenv("DATABASE_URL", "unused-test-url")
    monkeypatch.setattr(Cli, "create_async_engine", lambda url: engine)
    monkeypatch.setattr(
        Cli, "async_sessionmaker", lambda *args, **kwargs: backend.sessions
    )
    assert await Cli.run_recovery(backend.generation_id, uuid4()) == 1
    assert json.loads(capsys.readouterr().out) == {"error_kind": "LookupError"}
    assert backend.state().answer_recovery_attempts == 0
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_automatic_backoff_grows_with_durable_attempt_count(
    backend: Backend,
) -> None:
    item = backend
    now = datetime.now(UTC)
    for count, delay in enumerate((30, 60, 120, 240, 480), start=1):
        async with item.sessions() as session:
            claim = await Recovery.claim_answer_recovery(
                session,
                Types.ClaimAnswerRecoveryCommand(
                    generation_id=item.generation_id,
                    user_id=item.owner_id,
                    now=now,
                ),
            )
        assert claim.attempt_count == count
        actual = item.state().answer_recovery_next_at.replace(tzinfo=UTC)
        assert (actual - now).total_seconds() == delay
        # The exact deadline is eligible; no time.sleep or wall-clock dependency.
        now = actual
