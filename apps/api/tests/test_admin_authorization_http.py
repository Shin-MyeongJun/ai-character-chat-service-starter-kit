"""U24: real cookie/JWT and DB role policy with repository/domain doubles."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from test_identity_auth_contracts import Backend
from test_identity_auth_contracts import backend as backend_fixture
from test_identity_security import auth_settings as auth_settings_fixture

from app.db.models.character import Character
from app.db.models.identity import User
from app.db.models.lorebook import Lorebook
from app.http import character_dependencies, dependencies, lorebook_dependencies
from app.http.routes import router
from app.main import create_app
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service import command as CharacterCommandService
from app.modules.content.character.service import query as CharacterQueryService
from app.modules.content.character.service.command import change_character_status
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.lorebook.service import command as LorebookCommandService
from app.modules.content.lorebook.service import query as LorebookQueryService
from app.modules.content.lorebook.service.command import change_lorebook_status
from app.modules.identity.http_security import issue_csrf_token
from app.modules.identity.service import query as IdentityQueryService

auth_settings = auth_settings_fixture
backend = backend_fixture
TARGET_ID, ENTRY_ID = uuid4(), uuid4()
ROUTES = [
    ("GET", "/characters"),
    ("GET", f"/characters/{TARGET_ID}"),
    ("GET", "/lorebooks"),
    ("GET", f"/lorebooks/{TARGET_ID}"),
    ("GET", f"/lorebooks/{TARGET_ID}/entries"),
    ("GET", f"/lorebooks/{TARGET_ID}/entries/{ENTRY_ID}"),
    ("PATCH", "/characters/status"),
    ("PATCH", "/lorebooks/status"),
]


def request_body(path: str) -> dict[str, str] | None:
    if path.endswith("/status"):
        key = "character_id" if path.startswith("/characters") else "lorebook_id"
        # Identity claims in the body cannot replace the authenticated actor.
        return {key: str(TARGET_ID), "status": "approved", "owner_id": str(uuid4())}
    return None


@dataclass
class AdminHTTP:
    app: FastAPI
    backend: Backend
    operations: dict[str, AsyncMock]
    lookup: AsyncMock
    opened: list[AsyncSession]
    closed: list[AsyncSession]


@pytest.fixture
def admin_http(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> AdminHTTP:
    backend.user.role = "admin"
    app = create_app()
    app.state.authentication = backend.auth
    opened: list[AsyncSession] = []
    closed: list[AsyncSession] = []

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            opened.append(session)
            try:
                yield session
            finally:
                closed.append(session)

    app.state.session_factory = sessions
    lookup = AsyncMock(return_value=backend.user)
    monkeypatch.setattr(IdentityQueryService.Repository, "get_user", lookup)
    now = datetime.now(UTC)
    character = CharacterTypes.CharacterInfo(
        TARGET_ID,
        uuid4(),
        "Private character",
        None,
        "Private prompt",
        "private",
        "approved",
        None,
        now,
        now,
    )
    lorebook = LorebookTypes.LorebookInfo(
        TARGET_ID,
        uuid4(),
        "Private lorebook",
        None,
        "private",
        "approved",
        now,
        now,
    )
    entry = LorebookTypes.LorebookEntryInfo(
        ENTRY_ID,
        TARGET_ID,
        None,
        "Private entry",
        "world",
        "always",
        None,
        "contains",
        0,
        None,
        "before_history",
        True,
        {},
        now,
        now,
    )
    operations: dict[str, AsyncMock] = {}
    for module, name, value in (
        (
            CharacterQueryService,
            "list_characters",
            CharacterTypes.CharacterPage([character], None),
        ),
        (CharacterQueryService, "get_character_by_id", character),
        (
            LorebookQueryService,
            "list_lorebooks",
            LorebookTypes.LorebookPage([lorebook], None),
        ),
        (LorebookQueryService, "get_lorebook_by_id", lorebook),
        (
            LorebookQueryService,
            "list_lorebook_entries",
            LorebookTypes.LorebookEntryPage([entry], None),
        ),
        (LorebookQueryService, "get_lorebook_entry", entry),
        (CharacterCommandService, "change_character_status", character),
        (LorebookCommandService, "change_lorebook_status", lorebook),
    ):
        operations[name] = AsyncMock(return_value=value)
        monkeypatch.setattr(module, name, operations[name])
    return AdminHTTP(app, backend, operations, lookup, opened, closed)


def install_cookies(client: AsyncClient, item: AdminHTTP) -> None:
    settings = item.backend.auth.settings
    csrf = issue_csrf_token(item.backend.auth)
    client.cookies.set(settings.cookie_name("access"), item.backend.login.access_token)
    client.cookies.set(settings.cookie_name("csrf"), csrf)
    client.headers.update({"Origin": settings.public_origin, "X-CSRF-Token": csrf})


def assert_no_domain_calls(item: AdminHTTP) -> None:
    for operation in item.operations.values():
        operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ROUTES)
async def test_active_admin_reaches_existing_routes_with_fresh_separate_sessions(
    admin_http: AdminHTTP,
    method: str,
    path: str,
) -> None:
    item = admin_http

    async def lookup(session: AsyncSession, user_id: UUID, *, refresh: bool) -> User:
        assert user_id == item.backend.user.id and refresh is True
        # Model the autobegin performed by a real SELECT, without a DB server.
        await session.begin()
        return item.backend.user

    item.lookup.side_effect = lookup
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        response = await client.request(method, path, json=request_body(path))
    assert response.status_code == 200, response.text
    item.lookup.assert_awaited_once()
    auth_session = item.lookup.await_args.args[0]
    for operation in item.operations.values():
        if not operation.await_count:
            continue
        business_session, command = operation.await_args.args
        assert business_session is not auth_session
        assert not business_session.in_transaction()
        if method == "PATCH":
            assert command.owner_id == item.backend.user.id
            assert command.status == "approved"
    assert len(item.opened) == len(item.closed) == 2
    assert not auth_session.in_transaction()
    # The status route and its guard share the same verified actor dependency.
    item.backend.operations["get_authenticated_session"].assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize(
    "role,status",
    [
        ("user", "active"),
        ("admin", "suspended"),
        ("admin", "banned"),
        ("moderator", "active"),
    ],
)
async def test_trusted_authentication_never_grants_roles(
    admin_http: AdminHTTP,
    method: str,
    path: str,
    role: str,
    status: str,
) -> None:
    item = admin_http
    item.backend.user.role, item.backend.user.status = role, status

    # An external identity provider supplies an ID, never an authorization grant.
    async def authenticated_actor() -> UUID:
        return item.backend.user.id

    item.app = create_app(authenticate=authenticated_actor)
    item.app.state.session_factory = item.backend.auth.sessions
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        response = await client.request(method, path, json=request_body(path))
    assert response.status_code == 403 and response.json()["detail"] == "forbidden"
    item.lookup.assert_awaited_once()
    assert_no_domain_calls(item)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ROUTES)
@pytest.mark.parametrize(
    "failure",
    ["user", "suspended", "revoked", "missing_cookie", "forged_cookie", "unconfigured"],
)
async def test_default_cookie_auth_denies_before_domain_calls(
    admin_http: AdminHTTP,
    method: str,
    path: str,
    failure: str,
) -> None:
    item = admin_http
    expected = 401
    if failure == "user":
        item.backend.user.role = "user"
        expected = 403
    elif failure == "suspended":
        item.backend.user.status = "suspended"
    elif failure == "revoked":
        item.backend.session.revoked_at = datetime.now(UTC)
    elif failure == "unconfigured":
        del item.app.state.authentication
        expected = 503
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        if failure == "missing_cookie":
            client.cookies.delete(item.backend.auth.settings.cookie_name("access"))
        elif failure == "forged_cookie":
            client.cookies.set(
                item.backend.auth.settings.cookie_name("access"), "forged-token"
            )
        response = await client.request(method, path, json=request_body(path))
    assert response.status_code == expected, response.text
    assert_no_domain_calls(item)
    if failure != "user":
        item.lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/characters/status", "/lorebooks/status"])
@pytest.mark.parametrize("failure", ["origin", "csrf"])
async def test_moderation_keeps_cookie_csrf_and_origin_checks(
    admin_http: AdminHTTP,
    path: str,
    failure: str,
) -> None:
    item = admin_http
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        client.headers.pop("Origin" if failure == "origin" else "X-CSRF-Token")
        response = await client.patch(path, json=request_body(path))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == (
        "origin_forbidden" if failure == "origin" else "csrf_failed"
    )
    item.lookup.assert_not_awaited()
    assert_no_domain_calls(item)


@pytest.mark.asyncio
async def test_role_revocation_and_missing_user_take_effect_with_same_cookie(
    admin_http: AdminHTTP,
) -> None:
    item = admin_http
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        assert (await client.get("/characters")).status_code == 200
        item.backend.user.role = "user"
        assert (await client.get("/characters")).status_code == 403
        item.lookup.return_value = None
        assert (await client.get("/characters")).status_code == 403
    assert item.operations["list_characters"].await_count == 1
    assert item.lookup.await_count == 3
    assert all(call.kwargs == {"refresh": True} for call in item.lookup.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ROUTES)
async def test_standalone_unconfigured_guards_remain_closed(
    admin_http: AdminHTTP, method: str, path: str
) -> None:
    app = FastAPI()
    app.include_router(router)
    for hook in (
        dependencies.get_product_session,
        character_dependencies.get_character_session,
        lorebook_dependencies.get_lorebook_session,
    ):
        app.dependency_overrides[hook] = lambda: object()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        response = await client.request(method, path, json=request_body(path))
    assert response.status_code == 503
    assert_no_domain_calls(admin_http)


@pytest.mark.asyncio
async def test_external_identity_without_authorization_database_is_503(
    admin_http: AdminHTTP,
) -> None:
    app = create_app(authenticate=lambda: admin_http.backend.user.id)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        response = await client.get("/characters")
    assert response.status_code == 503
    admin_http.lookup.assert_not_awaited()
    assert_no_domain_calls(admin_http)


@pytest.mark.asyncio
async def test_authorization_storage_errors_are_not_reported_as_permission_denials(
    admin_http: AdminHTTP,
) -> None:
    item = admin_http
    item.lookup.side_effect = RuntimeError("database unavailable")
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        with pytest.raises(RuntimeError, match="database unavailable"):
            await client.get("/characters")
    assert_no_domain_calls(item)
    assert len(item.opened) == len(item.closed) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["character", "lorebook"])
@pytest.mark.parametrize("owned", [True, False])
async def test_moderation_preserves_real_owner_scope_and_write_transaction(
    admin_http: AdminHTTP,
    monkeypatch: pytest.MonkeyPatch,
    resource: str,
    owned: bool,
) -> None:
    item = admin_http
    now = datetime.now(UTC)
    if resource == "character":
        module = CharacterCommandService
        operation = change_character_status
        entity = Character(
            id=TARGET_ID,
            owner_id=item.backend.user.id,
            name="Character",
            persona_prompt="Prompt",
            visibility="private",
            status="approved",
            created_at=now,
            updated_at=now,
        )
    else:
        module = LorebookCommandService
        operation = change_lorebook_status
        entity = Lorebook(
            id=TARGET_ID,
            owner_id=item.backend.user.id,
            title="Lorebook",
            visibility="private",
            status="approved",
            created_at=now,
            updated_at=now,
        )
    monkeypatch.setattr(module, f"change_{resource}_status", operation)
    read = AsyncMock(return_value=entity if owned else None)
    write = AsyncMock(return_value=entity)
    monkeypatch.setattr(module.Repository, f"get_{resource}_by_id_and_owner_id", read)
    monkeypatch.setattr(module.Repository, f"change_{resource}_status_command", write)

    async def role_lookup(
        session: AsyncSession, user_id: UUID, *, refresh: bool
    ) -> User:
        await session.begin()
        return item.backend.user

    item.lookup.side_effect = role_lookup
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        path = f"/{resource}s/status"
        response = await client.patch(path, json=request_body(path))
    assert response.status_code == (200 if owned else 404), response.text
    read.assert_awaited_once()
    business_session, target_id, owner_id = read.await_args.args
    assert target_id == TARGET_ID and owner_id == item.backend.user.id
    assert read.await_args.kwargs == {"for_update": True}
    assert business_session is not item.lookup.await_args.args[0]
    assert not business_session.in_transaction()
    if owned:
        write.assert_awaited_once()
        assert write.await_args.args[1].owner_id == item.backend.user.id
    else:
        write.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_owner_routes_remain_available_to_users(
    admin_http: AdminHTTP,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = admin_http
    item.backend.user.role = "user"
    own_query = AsyncMock(return_value=LorebookTypes.LorebookPage([], None))
    monkeypatch.setattr(LorebookQueryService, "list_lorebooks_by_owner_id", own_query)
    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        response = await client.get("/lorebooks/me")
    assert response.status_code == 200
    assert own_query.await_args.args[1].owner_id == item.backend.user.id
    item.lookup.assert_not_awaited()
    assert_no_domain_calls(item)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", ROUTES)
async def test_verified_external_identity_uses_same_database_authorization(
    admin_http: AdminHTTP,
    method: str,
    path: str,
) -> None:
    item = admin_http
    app = create_app(authenticate=lambda: item.backend.user.id)
    app.state.session_factory = item.backend.auth.sessions
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        response = await client.request(method, path, json=request_body(path))
    assert response.status_code == 200, response.text
    item.lookup.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("role,expected", [("admin", 200), ("user", 403)])
async def test_reserved_product_admin_hook_uses_same_policy(
    admin_http: AdminHTTP,
    role: str,
    expected: int,
) -> None:
    item = admin_http
    item.backend.user.role = role

    @item.app.get(
        "/product-admin-guard-probe",
        dependencies=[Depends(dependencies.require_product_admin)],
    )
    async def guarded_probe() -> dict[str, bool]:
        return {"authorized": True}

    async with AsyncClient(
        transport=ASGITransport(app=item.app), base_url="https://testserver"
    ) as client:
        install_cookies(client, item)
        response = await client.get("/product-admin-guard-probe")
    assert response.status_code == expected
    item.lookup.assert_awaited_once()
