"""Offline identity storage/mapping contracts; no database or external providers."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import assert_type
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import AuthActionToken, AuthSession, User
from app.modules.identity import repository as Repository
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper
from app.modules.identity.service import query as QueryService

NOW = datetime(2026, 10, 28, tzinfo=UTC)
AccessQuery = Callable[
    [AsyncSession, Types.GetUserCommand], Awaitable[Types.UserAccessInfo]
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "lookup,role,status,allowed,message",
    [
        (QueryService.require_admin, "admin", "active", True, ""),
        (
            QueryService.require_admin,
            "user",
            "active",
            False,
            "Administrative operation unavailable.",
        ),
        (
            QueryService.require_admin,
            "moderator",
            "active",
            False,
            "Administrative operation unavailable.",
        ),
        (
            QueryService.require_admin,
            "admin",
            "suspended",
            False,
            "Administrative operation unavailable.",
        ),
        (
            QueryService.require_admin,
            "admin",
            "banned",
            False,
            "Administrative operation unavailable.",
        ),
        (
            QueryService.require_admin,
            None,
            None,
            False,
            "Administrative operation unavailable.",
        ),
        (QueryService.require_active_user, "user", "active", True, ""),
        (QueryService.require_active_user, "admin", "active", True, ""),
        (
            QueryService.require_active_user,
            "user",
            "suspended",
            False,
            "Active user unavailable.",
        ),
        (
            QueryService.require_active_user,
            "user",
            "banned",
            False,
            "Active user unavailable.",
        ),
        (
            QueryService.require_active_user,
            None,
            None,
            False,
            "Active user unavailable.",
        ),
    ],
)
async def test_access_queries_refresh_and_preserve_lookup_policy(
    lookup: AccessQuery,
    role: str | None,
    status: str | None,
    allowed: bool,
    message: str,
) -> None:
    user_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = (
        User(id=user_id, role=role, status=status) if role is not None else None
    )
    command = Types.GetUserCommand(user_id=user_id)
    if allowed:
        assert role is not None and status is not None
        info = await lookup(session, command)
        assert info == Types.UserAccessInfo(id=user_id, role=role, status=status)
    else:
        with pytest.raises(LookupError) as error:
            await lookup(session, command)
        assert str(error.value) == message
    session.get.assert_awaited_once_with(User, user_id, populate_existing=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["active", "suspended", "banned", None])
async def test_reportable_lookup_checks_existence_only(status: str | None) -> None:
    user_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = (
        User(id=user_id, role="user", status=status) if status is not None else None
    )
    command = Types.GetUserCommand(user_id=user_id)
    if status is None:
        with pytest.raises(LookupError, match="^User unavailable\\.$"):
            await QueryService.get_reportable_user(session, command)
    else:
        assert await QueryService.get_reportable_user(session, command) == user_id
    session.get.assert_awaited_once_with(User, user_id, populate_existing=True)


@pytest.mark.asyncio
async def test_default_user_lookup_preserves_session_cache_contract() -> None:
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    session.get.return_value = None
    assert await Repository.get_user(session, user_id) is None
    session.get.assert_awaited_once_with(User, user_id, populate_existing=False)


@pytest.mark.parametrize("password_hash", [None, "", "stored-argon2-hash"])
@pytest.mark.parametrize("pending_expires_at", [None, NOW])
def test_user_mapping_preserves_nullable_credentials_and_stored_values(
    password_hash: str | None,
    pending_expires_at: datetime | None,
) -> None:
    entity = User(
        id=uuid4(),
        email="person@example.com",
        email_verified=False,
        password_hash=password_hash,
        pending_expires_at=pending_expires_at,
        role="user",
        status="suspended",
    )
    info = assert_type(
        PersistenceMapper.user_entity_to_credential_info(entity), Types.CredentialInfo
    )
    assert info.user == Types.UserInfo(entity.id, entity.email, False)
    assert info.password_hash == password_hash
    assert info.pending_expires_at == pending_expires_at
    assert info.status == "suspended"
    assert assert_type(
        PersistenceMapper.user_entity_to_access_info(entity), Types.UserAccessInfo
    ) == Types.UserAccessInfo(entity.id, "user", "suspended")


@pytest.mark.parametrize("terminal_at", [None, NOW])
def test_session_and_action_mapping_preserves_ids_hashes_and_times(
    terminal_at: datetime | None,
) -> None:
    user_id, session_id, token_id = uuid4(), uuid4(), uuid4()
    expires_at = NOW + timedelta(minutes=15)
    session_entity = AuthSession(
        id=session_id,
        user_id=user_id,
        refresh_hash="stored-sha256-hash",
        expires_at=expires_at,
        revoked_at=terminal_at,
    )
    session_info = assert_type(
        PersistenceMapper.session_entity_to_info(session_entity), Types.SessionInfo
    )
    assert session_info == Types.SessionInfo(
        id=session_id,
        user_id=user_id,
        refresh_hash="stored-sha256-hash",
        expires_at=expires_at,
        revoked_at=terminal_at,
    )
    action_entity = AuthActionToken(
        id=token_id,
        user_id=user_id,
        purpose="reset",
        expires_at=expires_at,
        consumed_at=terminal_at,
    )
    assert assert_type(
        PersistenceMapper.action_entity_to_info(action_entity), Types.ActionTokenInfo
    ) == Types.ActionTokenInfo(
        id=token_id,
        user_id=user_id,
        purpose="reset",
        expires_at=expires_at,
        consumed_at=terminal_at,
    )
    assert "stored-sha256-hash" not in repr(session_info)


def test_missing_entities_are_distinct_from_nullable_fields() -> None:
    assert assert_type(PersistenceMapper.user_entity_to_access_info(None), None) is None
    assert (
        assert_type(PersistenceMapper.user_entity_to_credential_info(None), None)
        is None
    )
    assert assert_type(PersistenceMapper.session_entity_to_info(None), None) is None
    assert assert_type(PersistenceMapper.action_entity_to_info(None), None) is None


@pytest.mark.parametrize(
    "value,used", [(None, False), (0, True), ("", True), (uuid4(), True)]
)
def test_scalar_success_means_present_including_falsey_values(
    value: UUID | str | int | None, used: bool
) -> None:
    assert PersistenceMapper.scalar_row_to_used(value) is used


@pytest.mark.asyncio
async def test_locked_entity_queries_preserve_filters_and_missing_results() -> None:
    session = AsyncMock(spec=AsyncSession)
    scalar_rows = Mock()
    scalar_rows.first.return_value = None
    session.scalars.return_value = scalar_rows
    user_id, session_id = uuid4(), uuid4()

    assert await Repository.get_user_by_email(session, "person@example.com") is None
    assert await Repository.get_locked_user(session, user_id) is None
    assert await Repository.get_google_user(session, "provider-sub") is None
    assert await Repository.get_session(session, session_id) is None
    assert await Repository.get_action_token(session, "stored-token-hash") is None
    statements = [
        call.args[0].compile(dialect=postgresql.dialect())
        for call in session.scalars.await_args_list
    ]
    email, user, google, login_session, token = statements
    assert "users.email =" in str(email) and "FOR UPDATE" in str(email)
    assert "person@example.com" in email.params.values()
    assert "users.id =" in str(user) and "FOR UPDATE" in str(user)
    assert user_id in user.params.values()
    assert "users.id = user_oauth_accounts.user_id" in str(google)
    assert "user_oauth_accounts.provider =" in str(google)
    assert "user_oauth_accounts.provider_user_id =" in str(google)
    assert {"google", "provider-sub"} <= set(google.params.values())
    assert "FOR UPDATE OF users" in str(google)
    assert "auth_sessions.id =" in str(login_session)
    assert session_id in login_session.params.values()
    assert "FOR UPDATE" in str(login_session)
    assert "auth_action_tokens.token_hash =" in str(token)
    assert "stored-token-hash" in token.params.values()
    assert "FOR UPDATE" not in str(token)


@pytest.mark.asyncio
async def test_token_consumption_preserves_single_use_and_db_expiry() -> None:
    session = AsyncMock(spec=AsyncSession)
    token_id = uuid4()
    session.scalar.side_effect = [token_id, None, "stored-state-hash", None]
    assert await Repository.consume_action_token(session, token_id, NOW) == token_id
    assert await Repository.consume_action_token(session, token_id, NOW) is None
    assert (
        await Repository.consume_oauth_attempt(session, "stored-state-hash", NOW)
        == "stored-state-hash"
    )
    assert (
        await Repository.consume_oauth_attempt(session, "stored-state-hash", NOW)
        is None
    )
    for call in session.scalar.await_args_list:
        compiled = call.args[0].compile(dialect=postgresql.dialect())
        sql = str(compiled)
        assert "consumed_at IS NULL" in sql
        assert "expires_at > clock_timestamp()" in sql
        assert "RETURNING" in sql
        assert NOW in compiled.params.values()
        assert (
            token_id in compiled.params.values()
            or "stored-state-hash" in compiled.params.values()
        )


@pytest.mark.asyncio
async def test_cleanup_preserves_deletion_order_and_exact_counts() -> None:
    session = AsyncMock(spec=AsyncSession)
    counts: Repository.CleanupRow = (0, 2, 3, 4, 5)
    session.execute.side_effect = [Mock(rowcount=count) for count in counts]
    row = await Repository.delete_expired_records(session, NOW)
    assert row == counts
    assert PersistenceMapper.cleanup_row_to_info(row) == Types.CleanupInfo(
        0, 2, 3, 4, 5
    )
    tables = [
        "users",
        "auth_action_tokens",
        "auth_sessions",
        "auth_oauth_attempts",
        "auth_rate_limits",
    ]
    for call, table in zip(session.execute.await_args_list, tables, strict=True):
        compiled = call.args[0].compile(dialect=postgresql.dialect())
        assert str(compiled).startswith(f"DELETE FROM {table} WHERE")
        assert NOW in compiled.params.values()
        if table == "users":
            assert "users.email_verified IS false" in str(compiled)
            assert "users.pending_expires_at <=" in str(compiled)
    session.commit.assert_not_awaited()
    session.rollback.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_create_user_preserves_email_conflict_and_nullable_storage(
    conflict: bool,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    created_user = None if conflict else User(id=user_id)
    result = Mock()
    result.scalar_one_or_none.return_value = created_user
    session.execute.return_value = result
    assert (
        await Repository.create_user(
            session,
            user_id=user_id,
            email="normalized@example.com",
            password_hash=None,
            verified=True,
            pending_expires_at=None,
        )
        is created_user
    )
    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (email) DO NOTHING RETURNING " in str(compiled)
    assert set(str(compiled).split(" RETURNING ", 1)[1].split(", ")) == {
        f"users.{column.name}" for column in User.__table__.columns
    }
    assert compiled.params == {
        "id": user_id,
        "email": "normalized@example.com",
        "password_hash": None,
        "email_verified": True,
        "pending_expires_at": None,
    }
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_verify_email_keeps_required_entity_return(missing: bool) -> None:
    session = AsyncMock(spec=AsyncSession)
    user_id = uuid4()
    verified_user = User(
        id=user_id,
        email="person@example.com",
        email_verified=True,
        password_hash=None,
        pending_expires_at=None,
        status="active",
    )
    result = Mock()
    result.scalar_one.return_value = verified_user
    if missing:
        result.scalar_one.side_effect = NoResultFound
    session.execute.return_value = result
    if missing:
        with pytest.raises(NoResultFound):
            await Repository.verify_user_email(session, user_id)
    else:
        entity = await Repository.verify_user_email(session, user_id)
        assert (
            PersistenceMapper.user_entity_to_credential_info(entity).user.id == user_id
        )
    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert set(str(compiled).split(" RETURNING ", 1)[1].split(", ")) == {
        f"users.{column.name}" for column in User.__table__.columns
    }
    assert compiled.params == {
        "email_verified": True,
        "pending_expires_at": None,
        "id_1": user_id,
    }


@pytest.mark.asyncio
async def test_session_creation_and_rotation_keep_hash_and_absolute_expiry() -> None:
    session = AsyncMock(spec=AsyncSession)
    user_id, session_id = uuid4(), uuid4()
    expires_at = NOW + timedelta(days=14)
    await Repository.create_session(
        session,
        session_id=session_id,
        user_id=user_id,
        refresh_hash="original-refresh-hash",
        now=NOW,
        expires_at=expires_at,
    )
    await Repository.rotate_session(session, session_id, "rotated-refresh-hash")
    create, rotate = [
        call.args[0].compile(dialect=postgresql.dialect())
        for call in session.execute.await_args_list
    ]
    assert create.params == {
        "id": session_id,
        "user_id": user_id,
        "refresh_hash": "original-refresh-hash",
        "created_at": NOW,
        "expires_at": expires_at,
    }
    assert rotate.params == {"refresh_hash": "rotated-refresh-hash", "id_1": session_id}
    assert "WHERE auth_sessions.id =" in str(rotate)
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", [None, "verify", "reset"])
async def test_revocation_and_invalidation_preserve_unconsumed_scope(
    purpose: str | None,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    user_id, session_id = uuid4(), uuid4()
    await Repository.revoke_session(session, session_id, NOW)
    await Repository.revoke_user_sessions(session, user_id, NOW)
    await Repository.invalidate_action_tokens(session, user_id, purpose, NOW)
    revoke_one, revoke_all, invalidate = [
        call.args[0].compile(dialect=postgresql.dialect())
        for call in session.execute.await_args_list
    ]
    assert "auth_sessions.id =" in str(revoke_one)
    assert "auth_sessions.user_id =" in str(revoke_all)
    assert session_id in revoke_one.params.values()
    assert user_id in revoke_all.params.values()
    for revoke in (revoke_one, revoke_all):
        assert "auth_sessions.revoked_at IS NULL" in str(revoke)
        assert NOW in revoke.params.values()
    assert "auth_action_tokens.user_id =" in str(invalidate)
    assert "auth_action_tokens.consumed_at IS NULL" in str(invalidate)
    assert NOW in invalidate.params.values()
    assert user_id in invalidate.params.values()
    if purpose is None:
        assert "auth_action_tokens.purpose =" not in str(invalidate)
    else:
        assert "auth_action_tokens.purpose =" in str(invalidate)
        assert purpose in invalidate.params.values()
