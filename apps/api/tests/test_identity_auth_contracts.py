"""Offline auth transaction/ownership contracts; repository and SMTP are doubles."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from test_identity_security import auth_settings as auth_settings_fixture

from app.db.models.identity import AuthActionToken, AuthSession, User
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as Mapper
from app.modules.identity.service import authentication as Service
from app.modules.identity.service.workflow.mail import AuthenticationMailWorkflow
from app.modules.identity.settings import AuthSettings

auth_settings = auth_settings_fixture
PASSWORD = "long test password 123!"


@dataclass
class Backend:
    auth: Service.AuthenticationService
    user: User
    session: AuthSession
    action: AuthActionToken
    login: Types.LoginInfo
    events: list[str]
    operations: dict[str, AsyncMock]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch, auth_settings: AuthSettings) -> Backend:
    # Flow tests use small real Argon2 parameters; production parameters are tested
    # separately by test_identity_security, not asserted by this fixture.
    hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(Security, "PASSWORD_HASHER", hasher)
    monkeypatch.setattr(Security, "DUMMY_HASH", hasher.hash("dummy password"))
    events: list[str] = []

    def committed(session: Session) -> None:
        events.append("commit")

    def rolled_back(session: Session) -> None:
        events.append("rollback")

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            event.listen(session.sync_session, "after_commit", committed)
            event.listen(session.sync_session, "after_rollback", rolled_back)
            yield session

    auth = Service.AuthenticationService(sessions, auth_settings)
    now = datetime.now(UTC)
    user = User(
        id=uuid4(),
        email="person@example.com",
        email_verified=True,
        status="active",
        role="user",
        password_hash=hasher.hash(PASSWORD),
        pending_expires_at=None,
    )
    stored = AuthSession(
        id=uuid4(),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(hours=2),
        revoked_at=None,
    )
    login = auth._encode_login(
        Mapper.user_entity_to_credential_info(user).user,
        stored.id,
        now,
        stored.expires_at,
    )
    stored.refresh_hash = Security.token_hash(login.refresh_token)
    action = AuthActionToken(
        id=uuid4(),
        user_id=user.id,
        purpose="reset",
        token_hash="hash",
        expires_at=now + timedelta(minutes=1),
        consumed_at=None,
    )

    async def locked_user(session: AsyncSession, user_id: object) -> User:
        events.append("user")
        return user

    async def locked_session(session: AsyncSession, session_id: object) -> AuthSession:
        events.append("session")
        return stored

    async def read_authenticated_session(
        session: AsyncSession, user_id: object, session_id: object
    ) -> Service.Repository.AuthenticatedSessionRow:
        events.append("read_auth")
        return Service.Repository.AuthenticatedSessionRow(user, stored)

    operations = {
        "get_authenticated_session": AsyncMock(side_effect=read_authenticated_session),
        "get_locked_user": AsyncMock(side_effect=locked_user),
        "get_session": AsyncMock(side_effect=locked_session),
        "get_action_token": AsyncMock(return_value=action),
        "consume_action_token": AsyncMock(return_value=action.id),
        "get_user_by_email": AsyncMock(return_value=user),
        "create_user": AsyncMock(return_value=user),
        "verify_user_email": AsyncMock(return_value=user),
        "increment_rate_limit": AsyncMock(return_value=1),
    }
    for name in (
        "revoke_session",
        "rotate_session",
        "create_session",
        "update_password",
        "invalidate_action_tokens",
        "revoke_user_sessions",
        "create_action_token",
        "create_mail_outbox",
        "lock_identity",
        "delete_pending_user",
    ):
        operations[name] = AsyncMock()
    for name, operation in operations.items():
        monkeypatch.setattr(Service.Repository, name, operation)
    return Backend(auth, user, stored, action, login, events, operations)


@pytest.mark.asyncio
async def test_refresh_reuse_commits_revocation_before_error(backend: Backend) -> None:
    item = backend
    item.session.refresh_hash = "a different stored hash"

    async def revoke(session: AsyncSession, session_id: object, now: datetime) -> None:
        assert session.in_transaction()
        item.events.append("revoke")

    item.operations["revoke_session"].side_effect = revoke
    with pytest.raises(Types.AuthError, match="refresh_reused"):
        await item.auth.refresh_session(Types.TokenCommand(item.login.refresh_token))
    assert item.events == ["user", "session", "revoke", "commit"]
    item.operations["rotate_session"].assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_rotates_hash_without_extending_absolute_expiry(
    backend: Backend,
) -> None:
    item = backend
    login = await item.auth.refresh_session(
        Types.TokenCommand(item.login.refresh_token)
    )
    assert login.expires_at == item.session.expires_at
    assert login.refresh_token != item.login.refresh_token
    rotation = item.operations["rotate_session"].await_args
    assert rotation is not None
    assert rotation.args[1:] == (
        item.session.id,
        Security.token_hash(login.refresh_token),
    )
    assert item.events == ["user", "session", "commit"]
    item.operations["revoke_session"].assert_not_awaited()
    claims = item.auth.codec.decode_token(login.access_token, "access")
    assert claims["sub"] == str(item.user.id)
    assert claims["sid"] == str(item.session.id)
    assert login.access_token not in repr(login) and login.refresh_token not in repr(
        login
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["missing", "suspended", "unverified", "owner", "revoked", "expired"]
)
async def test_access_revalidates_user_and_session_before_returning_identity(
    backend: Backend, invalid: str
) -> None:
    item = backend
    if invalid == "missing":
        item.operations["get_authenticated_session"].side_effect = None
        item.operations["get_authenticated_session"].return_value = None
    elif invalid == "suspended":
        item.user.status = "suspended"
    elif invalid == "unverified":
        item.user.email_verified = False
    elif invalid == "owner":
        item.session.user_id = uuid4()
    elif invalid == "revoked":
        item.session.revoked_at = datetime.now(UTC)
    else:
        item.session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(Types.AuthError, match="invalid_session"):
        await item.auth.get_authenticated_user(
            Types.TokenCommand(item.login.access_token)
        )
    assert item.events[-1] == "rollback"
    item.operations["rotate_session"].assert_not_awaited()


@pytest.mark.asyncio
async def test_issue_session_stores_hash_and_preserves_access_and_absolute_limits(
    backend: Backend,
) -> None:
    item = backend
    now = datetime.now(UTC)
    async with AsyncSession() as session:
        login = await item.auth.issue_session(
            session,
            Types.IssueSessionCommand(
                Mapper.user_entity_to_credential_info(item.user), now
            ),
        )
    stored = item.operations["create_session"].await_args
    assert stored is not None
    assert stored.kwargs["refresh_hash"] == Security.token_hash(login.refresh_token)
    assert stored.kwargs["expires_at"] == now + timedelta(
        seconds=item.auth.settings.session_seconds
    )
    assert login.expires_at == stored.kwargs["expires_at"]
    claims = item.auth.codec.decode_token(login.access_token, "access")
    assert claims["exp"] == int(
        (now + timedelta(seconds=item.auth.settings.access_seconds)).timestamp()
    )


@pytest.mark.asyncio
async def test_reset_consumes_token_then_changes_password_and_revokes_sessions(
    backend: Backend,
) -> None:
    item = backend
    await item.auth.reset_password(Types.ResetPasswordCommand("raw token", PASSWORD))
    for name in (
        "consume_action_token",
        "update_password",
        "invalidate_action_tokens",
        "revoke_user_sessions",
    ):
        item.operations[name].assert_awaited_once()
    update = item.operations["update_password"].await_args
    assert update is not None
    assert Security.verify_password(PASSWORD, update.args[2])
    assert item.events == ["user", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["expired", "used", "purpose", "race"])
async def test_invalid_or_raced_action_never_changes_password_or_revokes_sessions(
    backend: Backend, invalid: str
) -> None:
    item = backend
    if invalid == "expired":
        item.action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif invalid == "used":
        item.action.consumed_at = datetime.now(UTC)
    elif invalid == "purpose":
        item.action.purpose = "verify"
    else:
        item.operations["consume_action_token"].return_value = None
    with pytest.raises(Types.AuthError, match="invalid_action_token"):
        await item.auth.reset_password(
            Types.ResetPasswordCommand("raw token", PASSWORD)
        )
    assert item.events[-1] == "rollback"
    for name in ("update_password", "invalidate_action_tokens", "revoke_user_sessions"):
        item.operations[name].assert_not_awaited()


@pytest.mark.asyncio
async def test_mail_request_commits_encrypted_outbox_without_calling_smtp(
    backend: Backend,
) -> None:
    item = backend
    item.user.email_verified = False
    item.user.pending_expires_at = datetime.now(UTC) + timedelta(days=7)
    item.operations["get_user_by_email"].return_value = None

    mailer = AsyncMock()
    mailer.send_mail.side_effect = Types.AuthError("mail_unavailable")
    await AuthenticationMailWorkflow(item.auth, mailer).register_user(
        Types.CredentialsCommand(item.user.email, PASSWORD)
    )
    created = item.operations["create_action_token"].await_args
    queued = item.operations["create_mail_outbox"].await_args
    assert created is not None and queued is not None
    raw_token = Security.decrypt_mail_token(
        queued.kwargs["encrypted_token"], created.kwargs["token_hash"], item.auth.settings
    )
    assert raw_token not in queued.kwargs["encrypted_token"]
    assert created.args[0] is queued.args[0]
    assert item.events[-1] == "commit"
    mailer.send_mail.assert_not_awaited()
    assert "rollback" not in item.events


@pytest.mark.asyncio
async def test_duplicate_registration_does_not_overwrite_credentials_or_send_mail(
    backend: Backend,
) -> None:
    item = backend
    mailer = AsyncMock()
    await AuthenticationMailWorkflow(item.auth, mailer).register_user(
        Types.CredentialsCommand(item.user.email, PASSWORD)
    )
    item.operations["create_user"].assert_not_awaited()
    item.operations["update_password"].assert_not_awaited()
    item.operations["create_action_token"].assert_not_awaited()
    mailer.send_mail.assert_not_awaited()


def test_claim_type_view_keeps_validated_extension_claims(backend: Backend) -> None:
    item = backend
    original = item.auth.codec.decode_token(item.login.access_token, "access")
    extension = {"nested": [None, True, "preserved"]}
    token = jwt.encode(
        {**original, "extension": extension}, item.auth.codec.key, algorithm="HS256"
    )
    decoded = item.auth.codec.decode_token(token, "access")
    assert decoded.get("extension") == extension
    assert decoded["sub"] == str(item.user.id)
    assert decoded["sid"] == str(item.session.id)
