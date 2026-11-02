"""Offline transaction ownership and PostgreSQL advisory-lock call contracts."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.idempotency import lock_key
from app.db.transaction import use_case_transaction


def track_transactions(session: AsyncSession) -> list[str]:
    events: list[str] = []

    def committed(session: Session) -> None:
        events.append("commit")

    def rolled_back(session: Session) -> None:
        events.append("rollback")

    event.listen(session.sync_session, "after_commit", committed)
    event.listen(session.sync_session, "after_rollback", rolled_back)
    return events


@pytest.mark.asyncio
async def test_nested_scopes_own_one_outer_commit() -> None:
    async with AsyncSession() as session:
        events = track_transactions(session)
        async with use_case_transaction(session):
            async with use_case_transaction(session):
                assert session.in_transaction()
            assert events == []
        assert events == ["commit"]
        assert not session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_caught_nested_error_or_cancellation_poison_outer_scope_only(
    cancelled: bool,
) -> None:
    async with AsyncSession() as session:
        events = track_transactions(session)
        with pytest.raises(RuntimeError, match="nested use case failed"):
            async with use_case_transaction(session):
                try:
                    async with use_case_transaction(session):
                        if cancelled:
                            raise asyncio.CancelledError
                        raise ValueError("nested failure")
                except (ValueError, asyncio.CancelledError):
                    pass
                assert events == []
        assert events == ["rollback"]
        assert not session.in_transaction()
        # Failure metadata must not poison a later independent use case.
        async with use_case_transaction(session):
            pass
        assert events == ["rollback", "commit"]


@pytest.mark.asyncio
async def test_unowned_existing_transaction_is_not_adopted_or_finished() -> None:
    async with AsyncSession() as session:
        events = track_transactions(session)
        await session.begin()
        with pytest.raises(InvalidRequestError):
            async with use_case_transaction(session):
                pytest.fail("Unowned transaction must not be adopted")
        assert events == []
        assert session.in_transaction()
        await session.rollback()
        assert events == ["rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "namespace,key,expected_id",
    [
        ("billing", "request-0", -4789477804764354572),
        ("검토", "요청-2", 1984750508653939788),
    ],
)
async def test_lock_uses_stable_signed_id_without_finishing_transaction(
    monkeypatch: pytest.MonkeyPatch,
    namespace: str,
    key: str,
    expected_id: int,
) -> None:
    async with AsyncSession() as session:
        execute = AsyncMock()
        monkeypatch.setattr(session, "execute", execute)
        events = track_transactions(session)
        async with use_case_transaction(session):
            await lock_key(session, namespace, key)
            call = execute.await_args
            assert call is not None
            assert str(call.args[0]) == "SELECT pg_advisory_xact_lock(:key)"
            lock_id = call.args[1]["key"]
            assert lock_id == expected_id
            assert isinstance(lock_id, int) and -(2**63) <= lock_id < 2**63
            assert events == []
        assert events == ["commit"]


@pytest.mark.asyncio
async def test_lock_error_propagates_and_rolls_back_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("database unavailable")
    async with AsyncSession() as session:
        monkeypatch.setattr(session, "execute", AsyncMock(side_effect=failure))
        events = track_transactions(session)
        with pytest.raises(RuntimeError) as caught:
            async with use_case_transaction(session):
                await lock_key(session, "billing", "request-1")
        assert caught.value is failure
        assert events == ["rollback"]
