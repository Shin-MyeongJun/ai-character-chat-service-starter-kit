"""Offline SQL freshness and gated Argon2/auth-state interleavings, without PostgreSQL."""

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from argon2 import PasswordHasher
from sqlalchemy import Column, MetaData, Table, Uuid, create_engine, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from test_identity_auth_contracts import PASSWORD, Backend
from test_identity_auth_contracts import backend as backend_fixture
from test_identity_security import auth_settings as auth_settings_fixture

from app.db.models.identity import AuthSession, User
from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as Mapper

auth_settings = auth_settings_fixture
backend = backend_fixture


def _track_sessions(item: Backend) -> set[AsyncSession]:
    original = item.auth.sessions
    active: set[AsyncSession] = set()

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with original() as session:
            active.add(session)
            try:
                yield session
            finally:
                active.remove(session)

    item.auth.sessions = sessions
    return active


@pytest.mark.asyncio
@pytest.mark.parametrize("rehash", [False, True])
async def test_login_cpu_work_has_no_open_session_and_session_issue_is_locked(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, rehash: bool
) -> None:
    item = backend
    active = _track_sessions(item)
    hasher = PasswordHasher(time_cost=2 if rehash else 1, memory_cost=8, parallelism=1)
    hasher_spy = Mock(wraps=hasher)
    original_verify = Security.verify_password
    steps: list[str] = []

    def verify(password: str, encoded: str | None) -> bool:
        assert not active
        steps.append("verify")
        return original_verify(password, encoded)

    def encode(password: str) -> str:
        assert not active
        steps.append("rehash")
        return hasher.hash(password)

    async def locked_user(session: AsyncSession, user_id: UUID) -> User:
        assert session in active and session.in_transaction()
        steps.append("lock")
        return item.user

    async def create_session(session: AsyncSession, **fields: object) -> None:
        assert session in active and session.in_transaction()
        assert steps[-1] == "lock"
        steps.append("issue")

    hasher_spy.hash.side_effect = encode
    monkeypatch.setattr(Security, "PASSWORD_HASHER", hasher_spy)
    monkeypatch.setattr(Security, "verify_password", verify)
    item.operations["get_locked_user"].side_effect = locked_user
    item.operations["create_session"].side_effect = create_session
    login = await item.auth.login_user(
        Types.CredentialsCommand(item.user.email, PASSWORD)
    )
    assert login.user.id == item.user.id
    assert steps == (
        ["verify", "rehash", "lock", "issue"] if rehash else ["verify", "lock", "issue"]
    )
    assert not active
    item.operations["get_user_by_email"].assert_awaited_once()
    lookup = item.operations["get_user_by_email"].await_args
    assert lookup is not None and lookup.kwargs == {"lock": False}
    assert item.operations["update_password"].await_count == int(rehash)
    if rehash:
        update_call = item.operations["update_password"].await_args
        assert update_call is not None
        encoded = update_call.args[2]
        assert hasher.verify(encoded, PASSWORD) and not hasher.check_needs_rehash(
            encoded
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["verify", "rehash"])
async def test_reset_committed_during_cpu_work_prevents_stale_login_and_rehash(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    item = backend
    active = _track_sessions(item)
    hasher = PasswordHasher(time_cost=2, memory_cost=8, parallelism=1)
    hasher_spy = Mock(wraps=hasher)
    original_verify = Security.verify_password
    entered, release = threading.Event(), threading.Event()

    def wait_for_reset() -> None:
        assert not active
        entered.set()
        assert release.wait(timeout=10), "reset did not release the password worker"

    def verify(password: str, encoded: str | None) -> bool:
        if phase == "verify":
            wait_for_reset()
        return original_verify(password, encoded)

    def encode(password: str) -> str:
        if phase == "rehash" and password == PASSWORD:
            wait_for_reset()
        return hasher.hash(password)

    async def update_password(
        session: AsyncSession, user_id: UUID, encoded: str
    ) -> None:
        item.user.password_hash = encoded

    async def revoke_sessions(
        session: AsyncSession, user_id: UUID, now: datetime
    ) -> None:
        item.session.revoked_at = now

    hasher_spy.hash.side_effect = encode
    monkeypatch.setattr(Security, "PASSWORD_HASHER", hasher_spy)
    monkeypatch.setattr(Security, "verify_password", verify)
    item.operations["update_password"].side_effect = update_password
    item.operations["revoke_user_sessions"].side_effect = revoke_sessions
    task = asyncio.create_task(
        item.auth.login_user(Types.CredentialsCommand(item.user.email, PASSWORD))
    )
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        item.operations["get_locked_user"].assert_not_awaited()
        await item.auth.reset_password(
            Types.ResetPasswordCommand("reset-token", PASSWORD + "new")
        )
        assert item.events[-1] == "commit"
        reset_hash = item.user.password_hash
    finally:
        release.set()
        # Always collect the worker/task even if a gate assertion fails.
        result = await asyncio.gather(task, return_exceptions=True)
    assert len(result) == 1 and isinstance(result[0], Types.AuthError)
    assert result[0].code == "invalid_credentials"
    assert item.user.password_hash == reset_hash
    assert Security.verify_password(PASSWORD + "new", reset_hash)
    assert item.session.revoked_at is not None
    assert item.operations["update_password"].await_count == 1  # reset only
    item.operations["create_session"].assert_not_awaited()
    assert item.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_login_committing_first_is_included_in_waiting_password_reset(
    backend: Backend,
) -> None:
    item = backend
    original = item.auth.sessions
    user_lock = asyncio.Lock()
    owners: set[AsyncSession] = set()
    created, release, reset_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    issued: list[UUID] = []
    revoked: list[UUID] = []

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with original() as session:
            try:
                yield session
            finally:
                # Model PostgreSQL's transaction-scoped row lock; SQL shape is
                # tested separately. Transaction commit/rollback has run here.
                if session in owners:
                    owners.remove(session)
                    user_lock.release()

    async def locked_user(session: AsyncSession, user_id: UUID) -> User:
        if user_lock.locked():
            reset_waiting.set()
        await user_lock.acquire()
        owners.add(session)
        return item.user

    async def create_session(session: AsyncSession, **fields: object) -> None:
        assert session in owners
        session_id = fields["session_id"]
        assert isinstance(session_id, UUID)
        issued.append(session_id)
        created.set()
        await release.wait()

    async def update_password(
        session: AsyncSession, user_id: UUID, encoded: str
    ) -> None:
        assert session in owners
        item.user.password_hash = encoded

    async def revoke_sessions(
        session: AsyncSession, user_id: UUID, now: datetime
    ) -> None:
        assert session in owners
        revoked.extend(issued)

    item.auth.sessions = sessions
    item.operations["get_locked_user"].side_effect = locked_user
    item.operations["create_session"].side_effect = create_session
    item.operations["update_password"].side_effect = update_password
    item.operations["revoke_user_sessions"].side_effect = revoke_sessions
    login_task = asyncio.create_task(
        item.auth.login_user(Types.CredentialsCommand(item.user.email, PASSWORD))
    )
    reset_task: asyncio.Task[None] | None = None
    try:
        await asyncio.wait_for(created.wait(), timeout=5)
        reset_task = asyncio.create_task(
            item.auth.reset_password(
                Types.ResetPasswordCommand("reset-token", PASSWORD + "new")
            )
        )
        await asyncio.wait_for(reset_waiting.wait(), timeout=5)
        item.operations["update_password"].assert_not_awaited()
        item.operations["revoke_user_sessions"].assert_not_awaited()
    finally:
        release.set()
        login_result = await asyncio.gather(login_task, return_exceptions=True)
        if reset_task is not None:
            await reset_task
    assert isinstance(login_result[0], Types.LoginInfo)
    claims = item.auth.codec.decode_token(login_result[0].access_token, "access")
    assert issued == revoked == [UUID(claims["sid"])]
    assert not owners and not user_lock.locked()
    assert item.events[-1] == "commit"


@pytest.mark.asyncio
async def test_session_insert_failure_rolls_back_rehash_transaction(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    item = backend
    monkeypatch.setattr(
        Security,
        "PASSWORD_HASHER",
        PasswordHasher(time_cost=2, memory_cost=8, parallelism=1),
    )
    failure = RuntimeError("session insert failed")
    item.operations["create_session"].side_effect = failure
    with pytest.raises(RuntimeError) as caught:
        await item.auth.login_user(Types.CredentialsCommand(item.user.email, PASSWORD))
    assert caught.value is failure
    item.operations["update_password"].assert_awaited_once()
    assert item.events[-2:] == ["user", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["missing", "suspended", "unverified", "email", "google_only", "rehash"]
)
async def test_final_locked_recheck_rejects_changed_credentials_or_account_state(
    backend: Backend, change: str
) -> None:
    item = backend

    async def changed_user(session: AsyncSession, user_id: UUID) -> User | None:
        if change == "missing":
            return None
        if change == "suspended":
            item.user.status = "suspended"
        elif change == "unverified":
            item.user.email_verified = False
        elif change == "email":
            item.user.email = "other@example.com"
        elif change == "google_only":
            item.user.password_hash = None
        else:
            item.user.password_hash = Security.PASSWORD_HASHER.hash(PASSWORD)
        return item.user

    item.operations["get_locked_user"].side_effect = changed_user
    with pytest.raises(Types.AuthError, match="invalid_credentials"):
        await item.auth.login_user(Types.CredentialsCommand(item.user.email, PASSWORD))
    item.operations["update_password"].assert_not_awaited()
    item.operations["create_session"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    ["missing", "password", "google_only", "suspended", "unverified", "malformed_hash"],
)
async def test_failed_credentials_still_verify_without_acquiring_user_lock(
    backend: Backend, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    item = backend
    if invalid == "missing":
        item.operations["get_user_by_email"].return_value = None
    elif invalid == "password":
        item.user.password_hash = Security.PASSWORD_HASHER.hash(
            "different password 123!"
        )
    elif invalid == "google_only":
        item.user.password_hash = None
    elif invalid == "suspended":
        item.user.status = "suspended"
    elif invalid == "unverified":
        item.user.email_verified = False
    else:
        item.user.password_hash = "malformed hash"
    verifier = Mock(wraps=Security.verify_password)
    monkeypatch.setattr(Security, "verify_password", verifier)
    with pytest.raises(Types.AuthError, match="invalid_credentials"):
        await item.auth.login_user(Types.CredentialsCommand(item.user.email, PASSWORD))
    verifier.assert_called_once_with(
        PASSWORD, None if invalid == "missing" else item.user.password_hash
    )
    item.operations["get_locked_user"].assert_not_awaited()
    item.operations["create_session"].assert_not_awaited()
    item.operations["update_password"].assert_not_awaited()


@pytest.mark.asyncio
async def test_access_uses_read_only_pair_while_mutating_auth_keeps_lock_order(
    backend: Backend,
) -> None:
    item = backend
    assert (
        await item.auth.get_authenticated_user(
            Types.TokenCommand(item.login.access_token)
        )
        == Mapper.user_entity_to_credential_info(item.user).user
    )
    assert item.events == ["read_auth", "commit"]
    item.operations["get_locked_user"].assert_not_awaited()
    item.operations["get_session"].assert_not_awaited()
    call = item.operations["get_authenticated_session"].await_args
    assert call is not None and call.args[1:] == (item.user.id, item.session.id)
    item.events.clear()
    await item.auth.logout_all_sessions(Types.TokenCommand(item.login.access_token))
    assert item.events == ["user", "session", "commit"]
    item.operations["revoke_user_sessions"].assert_awaited_once()


@pytest.mark.asyncio
async def test_read_queries_have_no_for_update_and_mutation_queries_refresh_cache() -> (
    None
):
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = Mock()
    session.execute.return_value.first.return_value = None
    session.scalars.return_value = Mock()
    session.scalars.return_value.first.return_value = None
    user_id, session_id = UUID(int=1), UUID(int=2)
    assert (
        await Repository.get_authenticated_session(session, user_id, session_id) is None
    )
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "JOIN auth_sessions ON auth_sessions.user_id = users.id" in sql
    assert "users.id =" in sql and "auth_sessions.id =" in sql
    assert set(compiled.params.values()) == {user_id, session_id}
    assert "FOR UPDATE" not in sql
    assert statement.get_execution_options()["populate_existing"] is True
    await Repository.get_user_by_email(session, "person@example.com", lock=False)
    read_statement = session.scalars.await_args.args[0]
    assert "FOR UPDATE" not in str(read_statement.compile(dialect=postgresql.dialect()))
    for operation, key in (
        (Repository.get_locked_user, user_id),
        (Repository.get_session, session_id),
    ):
        await operation(session, key)
        locked_statement = session.scalars.await_args.args[0]
        assert "FOR UPDATE" in str(
            locked_statement.compile(dialect=postgresql.dialect())
        )
        assert locked_statement.get_execution_options()["populate_existing"] is True


@pytest.fixture
def identity_database() -> Iterator[tuple[Session, AsyncMock]]:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    # Only columns: production FK/check/row-lock behavior requires PostgreSQL.
    for entity_type in (User, AuthSession):
        Table(
            entity_type.__tablename__,
            metadata,
            *(
                Column(
                    column.name,
                    Uuid(native_uuid=False)
                    if isinstance(column.type, Uuid)
                    else column.type,
                    primary_key=column.primary_key,
                )
                for column in entity_type.__table__.columns
            ),
        )
    metadata.create_all(engine)
    try:
        with Session(engine) as sync_session:
            session = AsyncMock(spec=AsyncSession)
            session.execute.side_effect = sync_session.execute
            session.scalars.side_effect = sync_session.scalars
            yield sync_session, session
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_auth_pair_and_locked_rechecks_replace_cached_state(
    identity_database: tuple[Session, AsyncMock],
) -> None:
    sync_session, session = identity_database
    now = datetime.now(UTC)
    user = User(
        id=UUID(int=1),
        email="person@example.com",
        email_verified=True,
        status="active",
        role="user",
        password_hash="before",
    )
    stored = AuthSession(
        id=UUID(int=2),
        user_id=user.id,
        refresh_hash="before",
        created_at=now,
        expires_at=now,
    )
    sync_session.add_all([user, stored])
    sync_session.flush()
    sync_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(status="suspended")
        .execution_options(synchronize_session=False)
    )
    sync_session.execute(
        update(AuthSession)
        .where(AuthSession.id == stored.id)
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    assert user.status == "active" and stored.revoked_at is None
    row = await Repository.get_authenticated_session(session, user.id, stored.id)
    infos = Mapper.authenticated_session_row_to_infos(row)
    assert (
        infos is not None
        and infos[0].status == "suspended"
        and infos[1].revoked_at is not None
    )
    assert (
        await Repository.get_authenticated_session(session, UUID(int=3), stored.id)
        is None
    )
    assert (
        await Repository.get_authenticated_session(session, user.id, UUID(int=3))
        is None
    )
    assert Mapper.authenticated_session_row_to_infos(None) is None
    sync_session.execute(
        update(User)
        .where(User.id == user.id)
        .values(password_hash="after")
        .execution_options(synchronize_session=False)
    )
    sync_session.execute(
        update(AuthSession)
        .where(AuthSession.id == stored.id)
        .values(refresh_hash="after")
        .execution_options(synchronize_session=False)
    )
    assert user.password_hash == "before" and stored.refresh_hash == "before"
    user_info = Mapper.user_entity_to_credential_info(
        await Repository.get_locked_user(session, user.id)
    )
    session_info = Mapper.session_entity_to_info(
        await Repository.get_session(session, stored.id)
    )
    assert user_info is not None and user_info.password_hash == "after"
    assert session_info is not None and session_info.refresh_hash == "after"
