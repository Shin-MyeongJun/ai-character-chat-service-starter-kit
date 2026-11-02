"""Worker lifetime, due-only draining and redacted CLI failures, without SMTP/DB."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from test_identity_security import auth_settings as auth_settings_fixture

from app import auth_mail_worker

auth_settings = auth_settings_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, True])
async def test_worker_drains_current_work_and_always_disposes_engine(
    monkeypatch, auth_settings, failure
):
    engine = MagicMock()
    engine.dispose = AsyncMock()
    create_engine = MagicMock(return_value=engine)
    monkeypatch.setattr(auth_mail_worker, "create_async_engine", create_engine)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(auth_mail_worker, "load_auth_settings", lambda: auth_settings)
    workflow = MagicMock()
    workflow.deliver_next_mail = AsyncMock(
        side_effect=RuntimeError("database down") if failure else [True, True, False]
    )
    monkeypatch.setattr(
        auth_mail_worker, "AuthenticationMailWorkflow", MagicMock(return_value=workflow)
    )
    if failure:
        with pytest.raises(RuntimeError, match="database down"):
            await auth_mail_worker.run_worker(once=True)
    else:
        await auth_mail_worker.run_worker(once=True)
        assert workflow.deliver_next_mail.await_count == 3
    engine.dispose.assert_awaited_once()
    assert create_engine.call_args.kwargs["hide_parameters"] is True


@pytest.mark.asyncio
async def test_worker_idle_poll_is_cancellable_and_disposes_engine(
    monkeypatch, auth_settings
):
    engine = MagicMock()
    engine.dispose = AsyncMock()
    monkeypatch.setattr(
        auth_mail_worker, "create_async_engine", MagicMock(return_value=engine)
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused/test")
    monkeypatch.setattr(auth_mail_worker, "load_auth_settings", lambda: auth_settings)
    workflow = MagicMock()
    workflow.deliver_next_mail = AsyncMock(return_value=False)
    monkeypatch.setattr(
        auth_mail_worker, "AuthenticationMailWorkflow", MagicMock(return_value=workflow)
    )
    sleep = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(auth_mail_worker.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await auth_mail_worker.run_worker(once=False)
    sleep.assert_awaited_once_with(1)
    engine.dispose.assert_awaited_once()


def test_cli_error_reports_only_exception_type(monkeypatch, caplog):
    monkeypatch.setattr("sys.argv", ["auth_mail_worker", "--once"])
    monkeypatch.setattr(
        auth_mail_worker,
        "run_worker",
        AsyncMock(side_effect=RuntimeError("private@example.com/#token=secret")),
    )
    with pytest.raises(SystemExit) as caught:
        auth_mail_worker.main()
    assert caught.value.code == 1
    assert "error_type=RuntimeError" in caplog.text
    assert "private@example.com" not in caplog.text and "secret" not in caplog.text
