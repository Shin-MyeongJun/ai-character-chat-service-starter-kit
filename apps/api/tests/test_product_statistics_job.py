"""Statistics CLI cleanup contracts without connecting to a database."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import statistics_job as Job
from app.modules.content.product import types


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repair", "failure"),
    [
        (False, None),
        (True, None),
        (True, "repair"),
        (True, "process"),
        (False, "cancel"),
    ],
)
async def test_job_closes_session_before_engine_disposal_and_propagates_failures(
    monkeypatch, capsys, repair, failure
):
    events = []
    session = AsyncSession(expire_on_commit=False)
    original_close = session.close
    error = (
        asyncio.CancelledError() if failure == "cancel" else RuntimeError("job failed")
    )

    async def close():
        await original_close()
        events.append("session_closed")

    async def dispose():
        assert not session.in_transaction()
        events.append("engine_disposed")

    async def enqueue(actual_session, command):
        assert actual_session is session
        assert command == types.EnqueueRecentCommand()
        events.append("repair")
        if failure == "repair":
            # Simulate a use-case error with an open transaction to exercise cleanup.
            await session.begin()
            raise error

    async def process(actual_session, command):
        assert actual_session is session
        assert command == types.ProcessPendingCommand(limit=17)
        events.append("process")
        await session.begin()
        if failure in ("process", "cancel"):
            raise error
        return types.ProcessedStatisticsInfo(processed=3)

    engine = SimpleNamespace(dispose=AsyncMock(side_effect=dispose))
    engine_factory = Mock(return_value=engine)
    session_factory = Mock(return_value=session)
    enqueue_service = AsyncMock(side_effect=enqueue)
    process_service = AsyncMock(side_effect=process)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://statistics.invalid/test")
    monkeypatch.setattr(Job, "create_async_engine", engine_factory)
    monkeypatch.setattr(Job, "AsyncSession", session_factory)
    monkeypatch.setattr(Job, "enqueue_recent", enqueue_service)
    monkeypatch.setattr(Job, "process_pending", process_service)
    monkeypatch.setattr(session, "close", close)

    if failure:
        with pytest.raises(type(error)) as caught:
            await Job.run(limit=17, repair=repair)
        assert caught.value is error
        assert capsys.readouterr().out == ""
    else:
        assert await Job.run(limit=17, repair=repair) is None
        assert capsys.readouterr().out == "Processed 3 product statistic days.\n"

    engine_factory.assert_called_once_with(
        "postgresql+asyncpg://statistics.invalid/test"
    )
    session_factory.assert_called_once_with(engine, expire_on_commit=False)
    engine.dispose.assert_awaited_once_with()
    expected = (["repair"] if repair else []) + (
        [] if failure == "repair" else ["process"]
    )
    assert events == expected + ["session_closed", "engine_disposed"]
    assert enqueue_service.await_count == int(repair)
    assert process_service.await_count == int(failure != "repair")
    assert not session.in_transaction()
