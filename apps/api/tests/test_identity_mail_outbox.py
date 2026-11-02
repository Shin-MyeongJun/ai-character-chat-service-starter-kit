"""U22: real HTTP contracts and PostgreSQL outbox atomicity, claims and retries."""

import asyncio
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import InvalidToken
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from test_identity_auth import csrf
from test_identity_auth import identity_db as identity_db_fixture
from test_identity_auth_contracts import Backend
from test_identity_auth_contracts import backend as backend_fixture
from test_identity_security import auth_settings as auth_settings_fixture

from app.db.models.identity import AuthActionToken, AuthMailOutbox, User
from app.main import create_app
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.adapters import SMTPMailSender
from app.modules.identity.service import (
    AuthenticationMailWorkflow,
    AuthenticationService,
)
from app.modules.identity.service import authentication as AuthenticationServiceModule
from app.modules.identity.service.mail_delivery import MailDeliveryService

PASSWORD = "outbox test password 123!"
EMAIL = "mail-outbox@example.com"
identity_db = identity_db_fixture
backend = backend_fixture
auth_settings = auth_settings_fixture


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", ["/auth/register", "/auth/email/resend", "/auth/password/reset/request"]
)
@pytest.mark.parametrize(
    "state", ["missing", "pending", "verified", "google", "suspended", "expired"]
)
@pytest.mark.parametrize("smtp", ["healthy", "unavailable", "blocked"])
async def test_http_acceptance_is_independent_of_account_and_smtp(
    backend: Backend, route, state, smtp
):
    item = backend
    item.user.email_verified = state in {"verified", "google", "suspended"}
    item.user.pending_expires_at = datetime.now(UTC) + timedelta(
        days=-1 if state == "expired" else 7
    )
    item.user.password_hash = None if state == "google" else "stored-password"
    item.user.status = "suspended" if state == "suspended" else "active"
    item.operations["get_user_by_email"].return_value = (
        None if state == "missing" else item.user
    )
    entered = asyncio.Event()

    async def send_mail(*args):
        entered.set()
        if smtp == "blocked":
            await asyncio.Event().wait()
        if smtp == "unavailable":
            raise Types.AuthError("mail_unavailable")

    mailer = AsyncMock()
    mailer.send_mail.side_effect = send_mail
    app = create_app()
    app.state.authentication = item.auth
    app.state.authentication_mail = AuthenticationMailWorkflow(item.auth, mailer)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await csrf(client)
        payload = {"email": item.user.email}
        if route == "/auth/register":
            payload["password"] = PASSWORD
        response = await asyncio.wait_for(client.post(route, json=payload), timeout=5)
    assert response.status_code == 202
    from app.modules.identity.schemas import AuthMessageResponseDto

    assert response.json() == AuthMessageResponseDto().model_dump()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "set-cookie" not in response.headers
    mailer.send_mail.assert_not_awaited()
    assert not entered.is_set()
    assert "rollback" not in item.events


@pytest.mark.asyncio
async def test_outbox_failure_is_not_reported_as_accepted(backend: Backend):
    backend.operations["get_user_by_email"].return_value = None
    backend.operations["create_mail_outbox"].side_effect = RuntimeError(
        "storage unavailable"
    )
    mailer = AsyncMock()
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await AuthenticationMailWorkflow(backend.auth, mailer).register_user(
            Types.CredentialsCommand(backend.user.email, PASSWORD)
        )
    assert backend.events[-1] == "rollback"
    mailer.send_mail.assert_not_awaited()


def test_encrypted_token_context_integrity_and_repr(auth_settings):
    token = Security.random_token()
    digest = Security.token_hash(token)
    encrypted = Security.encrypt_mail_token(token, auth_settings)
    assert token not in encrypted
    assert Security.decrypt_mail_token(encrypted, digest, auth_settings) == token
    with pytest.raises(InvalidToken):
        Security.decrypt_mail_token(encrypted, "different-proof", auth_settings)
    with pytest.raises(InvalidToken):
        Security.decrypt_mail_token(encrypted[:-3] + "abc", digest, auth_settings)
    from cryptography.fernet import Fernet

    wrong_context = Fernet(auth_settings.flow_key.encode()).encrypt(b"{}").decode()
    with pytest.raises(InvalidToken):
        Security.decrypt_mail_token(wrong_context, digest, auth_settings)
    info = Types.ActionMailInfo(EMAIL, "verify", token)
    assert EMAIL not in repr(info) and token not in repr(info)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,can_retry",
    [
        (OSError("sensitive connection detail"), True),
        (smtplib.SMTPDataError(451, b"sensitive temporary response"), True),
        (smtplib.SMTPDataError(550, b"sensitive permanent response"), False),
        (smtplib.SMTPAuthenticationError(535, b"sensitive auth response"), False),
        (smtplib.SMTPRecipientsRefused({EMAIL: (550, b"refused")}), False),
        (smtplib.SMTPRecipientsRefused({EMAIL: (450, b"retry")}), True),
        (smtplib.SMTPNotSupportedError("sensitive capability"), False),
    ],
)
async def test_smtp_failure_classification_preserves_public_adapter_code(
    auth_settings, monkeypatch, caplog, failure, can_retry
):
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(side_effect=failure))
    with pytest.raises(Types.MailDeliveryError) as caught:
        await SMTPMailSender(auth_settings).send_mail(
            EMAIL, "verify", "https://testserver/#token=private"
        )
    assert caught.value.code == "mail_unavailable"
    assert caught.value.can_retry is can_retry
    assert EMAIL not in caplog.text and "private" not in caplog.text


class Clock:
    def __init__(self):
        self.now = datetime.now(UTC)

    def __call__(self):
        return self.now


async def make_work(identity_db, auth_settings):
    auth = AuthenticationService(identity_db, auth_settings)
    mailer = AsyncMock()
    workflow = AuthenticationMailWorkflow(auth, mailer)
    action = await auth.register_pending_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    assert action is not None
    clock = Clock()
    workflow.delivery = MailDeliveryService(identity_db, auth_settings, clock=clock)
    return auth, workflow, mailer, action, clock


async def read_outbox(identity_db, token):
    async with identity_db() as session:
        return await session.scalar(
            select(AuthMailOutbox).where(
                AuthMailOutbox.token_hash == Security.token_hash(token)
            )
        )


@pytest.mark.asyncio
async def test_pg_commit_survives_new_worker_and_clears_payload_after_delivery(
    identity_db, auth_settings, caplog
):
    caplog.set_level(logging.INFO, logger="app.modules.identity.service.mail_delivery")
    auth, workflow, mailer, action, _ = await make_work(identity_db, auth_settings)
    stored = await read_outbox(identity_db, action.token)
    assert stored.status == "pending" and stored.attempt_count == 0
    assert action.token not in stored.encrypted_token
    assert (
        Security.decrypt_mail_token(
            stored.encrypted_token, stored.token_hash, auth_settings
        )
        == action.token
    )
    # Entirely new service/worker: no in-memory request or task is necessary.
    workflow = AuthenticationMailWorkflow(
        AuthenticationService(identity_db, auth_settings), mailer
    )
    assert await workflow.deliver_next_mail()
    mailer.send_mail.assert_awaited_once_with(
        EMAIL,
        "verify",
        auth_settings.public_origin + "/verify-email#token=" + action.token,
    )
    stored = await read_outbox(identity_db, action.token)
    assert stored.status == "sent" and stored.encrypted_token is None
    assert stored.attempt_count == 1 and stored.claim_token is None
    assert not await workflow.deliver_next_mail()
    assert (await auth.verify_email(Types.TokenCommand(action.token))).email_verified
    with pytest.raises(Types.AuthError, match="invalid_action_token"):
        await auth.verify_email(Types.TokenCommand(action.token))
    assert "status=sent" in caplog.text
    assert EMAIL not in caplog.text and action.token not in caplog.text


@pytest.mark.asyncio
async def test_pg_queue_write_failure_rolls_back_account_proof_and_outbox(
    identity_db, auth_settings, monkeypatch
):
    original = AuthenticationServiceModule.Repository.create_mail_outbox

    async def fail_after_insert(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("after outbox insert")

    monkeypatch.setattr(
        AuthenticationServiceModule.Repository, "create_mail_outbox", fail_after_insert
    )
    auth = AuthenticationService(identity_db, auth_settings)
    with pytest.raises(RuntimeError, match="after outbox insert"):
        await auth.register_pending_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    async with identity_db() as session:
        for model in (User, AuthActionToken, AuthMailOutbox):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_pg_failed_resend_preserves_previous_valid_proof(
    identity_db, auth_settings, monkeypatch
):
    auth, workflow, _, action, _ = await make_work(identity_db, auth_settings)
    monkeypatch.setattr(
        AuthenticationServiceModule.Repository,
        "create_mail_outbox",
        AsyncMock(side_effect=RuntimeError("queue down")),
    )
    with pytest.raises(RuntimeError, match="queue down"):
        await workflow.resend_verification(Types.EmailCommand(EMAIL))
    assert (await auth.verify_email(Types.TokenCommand(action.token))).email_verified


@pytest.mark.asyncio
async def test_pg_retry_uses_same_token_and_backoff_then_stops_at_five(
    identity_db, auth_settings, caplog
):
    caplog.set_level(logging.INFO, logger="app.modules.identity.service.mail_delivery")
    _, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    mailer.send_mail.side_effect = Types.MailDeliveryError(can_retry=True)
    for attempt in range(1, 6):
        assert await workflow.deliver_next_mail()
        stored = await read_outbox(identity_db, action.token)
        assert stored.attempt_count == attempt
        assert not await workflow.deliver_next_mail()
        if attempt < 5:
            delay = 30 * 2 ** (attempt - 1)
            assert (
                delay
                <= (stored.available_at - clock.now).total_seconds()
                <= delay * 1.25
            )
            assert stored.status == "pending" and stored.encrypted_token is not None
            clock.now = stored.available_at
        else:
            assert (
                stored.status == "failed" and stored.last_error == "attempts_exhausted"
            )
            assert stored.encrypted_token is None
    assert mailer.send_mail.await_count == 5
    assert len({call.args[2] for call in mailer.send_mail.await_args_list}) == 1
    assert EMAIL not in caplog.text and action.token not in caplog.text
    assert "attempt=5" in caplog.text and "reason=attempts_exhausted" in caplog.text


@pytest.mark.asyncio
async def test_pg_transient_failure_recovers_with_original_proof(
    identity_db, auth_settings
):
    auth, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    mailer.send_mail.side_effect = [Types.MailDeliveryError(can_retry=True), None]
    await workflow.deliver_next_mail()
    clock.now = (await read_outbox(identity_db, action.token)).available_at
    await workflow.deliver_next_mail()
    assert (await read_outbox(identity_db, action.token)).status == "sent"
    assert (await auth.verify_email(Types.TokenCommand(action.token))).email_verified


@pytest.mark.asyncio
async def test_pg_permanent_error_is_terminal(identity_db, auth_settings):
    _, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    mailer.send_mail.side_effect = Types.MailDeliveryError(can_retry=False)
    await workflow.deliver_next_mail()
    stored = await read_outbox(identity_db, action.token)
    assert stored.status == "failed" and stored.last_error == "smtp_permanent"
    assert stored.encrypted_token is None
    clock.now += timedelta(minutes=5)
    assert not await workflow.deliver_next_mail()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "expired",
        "consumed",
        "superseded",
        "suspended",
        "google",
        "pending_expired",
        "payload",
        "deleted",
    ],
)
async def test_pg_worker_drops_stale_or_ineligible_mail(
    identity_db, auth_settings, invalid
):
    auth, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    if invalid == "expired":
        clock.now += timedelta(minutes=31)
    elif invalid == "consumed":
        await auth.verify_email(Types.TokenCommand(action.token))
    elif invalid == "superseded":
        await workflow.resend_verification(Types.EmailCommand(EMAIL))
    elif invalid == "deleted":
        from sqlalchemy import delete

        async with identity_db.begin() as session:
            await session.execute(delete(User))
    else:
        async with identity_db.begin() as session:
            if invalid == "payload":
                await session.execute(
                    update(AuthMailOutbox).values(encrypted_token="corrupted")
                )
            else:
                changes = {
                    "suspended": {"status": "suspended"},
                    "google": {"password_hash": None},
                    "pending_expired": {
                        "pending_expires_at": clock.now - timedelta(seconds=1)
                    },
                }
                await session.execute(update(User).values(**changes[invalid]))
    processed = await workflow.deliver_next_mail()
    mailer.send_mail.assert_not_awaited()
    if invalid == "deleted":
        assert not processed and await read_outbox(identity_db, action.token) is None
    else:
        stored = await read_outbox(identity_db, action.token)
        assert stored.status == ("failed" if invalid == "payload" else "cancelled")
        assert stored.encrypted_token is None


@pytest.mark.asyncio
async def test_pg_concurrent_workers_claim_once_and_recover_expired_lease_with_fence(
    identity_db, auth_settings
):
    _, workflow, _, action, clock = await make_work(identity_db, auth_settings)
    other = MailDeliveryService(identity_db, auth_settings, clock=clock)
    claims = await asyncio.gather(workflow.delivery.claim_mail(), other.claim_mail())
    assert sum(claim is not None for claim in claims) == 1
    first = next(claim for claim in claims if claim is not None)
    # A dead worker cannot acknowledge, even before a second worker takes over.
    clock.now += timedelta(seconds=121)
    assert not await other.complete_mail(
        Types.CompleteMailDeliveryCommand(first.id, first.claim_token, "sent")
    )
    second = await other.claim_mail()
    assert second is not None and second.attempt_count == 2
    assert second.claim_token != first.claim_token
    assert second.mail.token == first.mail.token == action.token
    assert not await workflow.delivery.complete_mail(
        Types.CompleteMailDeliveryCommand(first.id, first.claim_token, "retry")
    )
    assert await other.complete_mail(
        Types.CompleteMailDeliveryCommand(second.id, second.claim_token, "sent")
    )
    assert (await read_outbox(identity_db, action.token)).status == "sent"


@pytest.mark.asyncio
async def test_pg_skip_locked_claim_progresses_to_other_mail(
    identity_db, auth_settings
):
    auth, workflow, _, action, clock = await make_work(identity_db, auth_settings)
    second = await auth.register_pending_user(
        Types.CredentialsCommand("second@example.com", PASSWORD)
    )
    clock.now = datetime.now(UTC)
    async with identity_db.begin() as session:
        await session.scalar(
            select(AuthMailOutbox)
            .where(AuthMailOutbox.token_hash == Security.token_hash(action.token))
            .with_for_update()
        )
        claim = await asyncio.wait_for(workflow.delivery.claim_mail(), timeout=3)
        assert claim.mail.token == second.token


@pytest.mark.asyncio
async def test_pg_smtp_wait_holds_no_user_or_outbox_locks(identity_db, auth_settings):
    auth, workflow, mailer, action, _ = await make_work(identity_db, auth_settings)
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_send(*args):
        entered.set()
        await release.wait()

    mailer.send_mail.side_effect = blocked_send
    task = asyncio.create_task(workflow.deliver_next_mail())
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        # The API can invalidate the proof while SMTP is blocked. An in-flight
        # old link may arrive, but using it must fail after this commit.
        await asyncio.wait_for(
            workflow.resend_verification(Types.EmailCommand(EMAIL)), timeout=3
        )
        async with identity_db.begin() as session:
            await session.scalar(
                select(AuthMailOutbox)
                .where(AuthMailOutbox.token_hash == Security.token_hash(action.token))
                .with_for_update(nowait=True)
            )
        with pytest.raises(Types.AuthError, match="invalid_action_token"):
            await auth.verify_email(Types.TokenCommand(action.token))
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_pg_cancellation_and_repeated_crashes_are_bounded(
    identity_db, auth_settings
):
    _, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    mailer.send_mail.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await workflow.deliver_next_mail()
    assert (await read_outbox(identity_db, action.token)).status == "processing"
    for attempt in range(2, 6):
        clock.now += timedelta(seconds=121)
        claim = await workflow.delivery.claim_mail()
        assert claim.attempt_count == attempt and claim.mail is not None
    clock.now += timedelta(seconds=121)
    claim = await workflow.delivery.claim_mail()
    assert claim.mail is None
    stored = await read_outbox(identity_db, action.token)
    assert stored.status == "failed" and stored.encrypted_token is None


@pytest.mark.asyncio
async def test_pg_retry_beyond_expiry_is_cancelled_and_cleanup_cascades(
    identity_db, auth_settings
):
    auth, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    async with identity_db.begin() as session:
        await session.execute(
            update(AuthActionToken).values(expires_at=clock.now + timedelta(seconds=10))
        )
    mailer.send_mail.side_effect = Types.AuthError("mail_unavailable")
    await workflow.deliver_next_mail()
    assert (await read_outbox(identity_db, action.token)).status == "cancelled"
    async with identity_db.begin() as session:
        await session.execute(
            update(AuthActionToken).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    await auth.cleanup_expired_auth()
    assert await read_outbox(identity_db, action.token) is None


@pytest.mark.asyncio
async def test_pg_smtp_acceptance_then_ack_rollback_redelivers_same_one_time_proof(
    identity_db, auth_settings, monkeypatch
):
    auth, workflow, mailer, action, clock = await make_work(identity_db, auth_settings)
    original = AuthenticationServiceModule.Repository.update_mail_outbox

    async def fail_ack_after_write(*args, **kwargs):
        await original(*args, **kwargs)
        if kwargs["status"] == "sent":
            raise RuntimeError("ack transaction interrupted")

    monkeypatch.setattr(
        AuthenticationServiceModule.Repository,
        "update_mail_outbox",
        fail_ack_after_write,
    )
    with pytest.raises(RuntimeError, match="ack transaction interrupted"):
        await workflow.deliver_next_mail()
    assert mailer.send_mail.await_count == 1
    stored = await read_outbox(identity_db, action.token)
    assert stored.status == "processing" and stored.encrypted_token is not None
    monkeypatch.setattr(
        AuthenticationServiceModule.Repository, "update_mail_outbox", original
    )
    clock.now += timedelta(seconds=121)
    assert await workflow.deliver_next_mail()
    assert mailer.send_mail.await_count == 2
    assert mailer.send_mail.await_args_list[0] == mailer.send_mail.await_args_list[1]
    assert (await read_outbox(identity_db, action.token)).status == "sent"
    await auth.verify_email(Types.TokenCommand(action.token))
    with pytest.raises(Types.AuthError, match="invalid_action_token"):
        await auth.verify_email(Types.TokenCommand(action.token))
