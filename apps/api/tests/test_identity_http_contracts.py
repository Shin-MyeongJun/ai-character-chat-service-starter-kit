"""Offline HTTP authentication contracts with real JWT/DTOs and service doubles."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Annotated
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from test_identity_auth_contracts import Backend
from test_identity_auth_contracts import backend as backend_fixture
from test_identity_google_contracts import RecordingVerifier
from test_identity_security import auth_settings as auth_settings_fixture

from app.modules.identity import schemas as Schemas
from app.modules.identity import types as Types
from app.modules.identity.dependencies import get_verified_user_id
from app.modules.identity.http_security import CookieCSRFMiddleware
from app.modules.identity.router import router
from app.modules.identity.service.workflow.google import GoogleLoginService
from app.modules.identity.service.workflow.mail import AuthenticationMailWorkflow

auth_settings = auth_settings_fixture
backend = backend_fixture
PASSWORD = "private password 123!"
TOKEN = "private-action-token-" + "x" * 32


@dataclass
class HTTPBackend:
    backend: Backend
    app: FastAPI
    operations: dict[str, AsyncMock]


@pytest.fixture
def http_backend(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> HTTPBackend:
    app = FastAPI()
    app.add_middleware(CookieCSRFMiddleware)
    app.include_router(router)
    app.state.authentication = backend.auth
    mail = AuthenticationMailWorkflow(backend.auth, AsyncMock())
    google = GoogleLoginService(backend.auth, RecordingVerifier(backend.events))
    app.state.authentication_mail = mail
    app.state.google_login = google
    operations: dict[str, AsyncMock] = {}
    for name in ("login_user", "refresh_session"):
        operations[name] = AsyncMock(return_value=backend.login)
    for name in ("get_authenticated_user", "verify_email"):
        operations[name] = AsyncMock(return_value=backend.login.user)
    for name in (
        "reset_password",
        "logout_session",
        "logout_all_sessions",
        "check_rate_limit",
    ):
        operations[name] = AsyncMock()
    for name, operation in operations.items():
        monkeypatch.setattr(backend.auth, name, operation)
    for name in ("register_user", "resend_verification", "request_password_reset"):
        operations[name] = AsyncMock()
        monkeypatch.setattr(mail, name, operations[name])
    operations["start_google_login"] = AsyncMock(
        return_value=Types.GoogleStartInfo(
            "https://accounts.google.com/example", "private-flow"
        )
    )
    operations["complete_google_login"] = AsyncMock(
        return_value=Types.GoogleLoginInfo(backend.login, "/account?tab=security")
    )
    monkeypatch.setattr(google, "start_google_login", operations["start_google_login"])
    monkeypatch.setattr(
        google, "complete_google_login", operations["complete_google_login"]
    )

    @app.api_route("/outside-auth", methods=["GET", "POST"])
    async def outside_auth() -> dict[str, bool]:
        return {"ok": True}

    @app.api_route("/verified-identity", methods=["GET", "POST"])
    async def verified_identity(
        user_id: Annotated[UUID, Depends(get_verified_user_id)],
    ) -> dict[str, str]:
        return {"id": str(user_id)}

    return HTTPBackend(backend, app, operations)


@pytest_asyncio.fixture
async def client(http_backend: HTTPBackend) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=http_backend.app), base_url="https://testserver"
    ) as client:
        response = await client.get("/auth/csrf")
        assert response.status_code == 200
        client.headers.update(
            {
                "Origin": "https://testserver",
                "X-CSRF-Token": response.json()["csrf_token"],
            }
        )
        http_backend.operations["check_rate_limit"].reset_mock()
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/auth/login", "/auth/refresh", "/auth/me", "/auth/email/verify"]
)
async def test_user_routes_project_only_public_identity_and_pass_commands(
    http_backend: HTTPBackend,
    client: AsyncClient,
    path: str,
) -> None:
    item = http_backend
    settings = item.backend.auth.settings
    client.cookies.set(settings.cookie_name("access"), "original-access")
    client.cookies.set(settings.cookie_name("refresh"), "original-refresh")
    command: Types.TokenCommand | Types.CredentialsCommand
    if path == "/auth/me":
        response = await client.get(path)
        name, command = "get_authenticated_user", Types.TokenCommand("original-access")
    elif path == "/auth/login":
        response = await client.post(
            path, json={"email": "person@example.com", "password": PASSWORD}
        )
        name, command = (
            "login_user",
            Types.CredentialsCommand("person@example.com", PASSWORD),
        )
    elif path == "/auth/refresh":
        response = await client.post(path)
        name, command = "refresh_session", Types.TokenCommand("original-refresh")
    else:
        response = await client.post(path, json={"token": TOKEN})
        name, command = "verify_email", Types.TokenCommand(TOKEN)
    user = item.backend.login.user
    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": user.email,
        "email_verified": True,
    }
    item.operations[name].assert_awaited_once_with(command)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert item.backend.login.access_token not in response.text
    assert item.backend.login.refresh_token not in response.text
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == (2 if name in {"login_user", "refresh_session"} else 0)
    for cookie in cookies:
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
        assert "Path=/" in cookie and "__Host-chatkit_" in cookie


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [-60, 60, 3600])
async def test_cookie_lifetimes_clamp_to_absolute_session_expiry(
    http_backend: HTTPBackend,
    client: AsyncClient,
    seconds: int,
) -> None:
    item = http_backend
    login = replace(
        item.backend.login, expires_at=datetime.now(UTC) + timedelta(seconds=seconds)
    )
    item.operations["login_user"].return_value = login
    response = await client.post(
        "/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    )
    cookies = response.headers.get_list("set-cookie")
    ages = [int(cookie.split("Max-Age=", 1)[1].split(";", 1)[0]) for cookie in cookies]
    assert response.status_code == 200
    if seconds < 0:
        assert ages == [0, 0]
    else:
        assert max(0, seconds - 2) <= ages[1] <= seconds
        assert ages[0] == min(900, ages[1])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,name",
    [
        ("/auth/register", "register_user"),
        ("/auth/email/resend", "resend_verification"),
        ("/auth/password/reset/request", "request_password_reset"),
    ],
)
async def test_mail_routes_return_same_message_without_exposing_account_state(
    http_backend: HTTPBackend,
    client: AsyncClient,
    path: str,
    name: str,
) -> None:
    body = {"email": "person@example.com"}
    if name == "register_user":
        body["password"] = PASSWORD
    response = await client.post(path, json=body)
    assert response.status_code == 202
    assert response.json() == Schemas.AuthMessageResponseDto().model_dump()
    assert not response.headers.get_list("set-cookie")
    expected = (
        Types.CredentialsCommand(body["email"], PASSWORD)
        if name == "register_user"
        else Types.EmailCommand(body["email"])
    )
    http_backend.operations[name].assert_awaited_once_with(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,name",
    [
        ("/auth/logout", "logout_session"),
        ("/auth/logout-all", "logout_all_sessions"),
        ("/auth/password/reset", "reset_password"),
    ],
)
async def test_session_end_routes_keep_empty_204_and_clear_all_four_cookies(
    http_backend: HTTPBackend,
    client: AsyncClient,
    path: str,
    name: str,
) -> None:
    settings = http_backend.backend.auth.settings
    client.cookies.set(settings.cookie_name("access"), "original-access")
    client.cookies.set(settings.cookie_name("refresh"), "original-refresh")
    if name == "reset_password":
        response = await client.post(path, json={"token": TOKEN, "password": PASSWORD})
        command: (
            Types.ResetPasswordCommand | Types.LogoutCommand | Types.TokenCommand
        ) = Types.ResetPasswordCommand(TOKEN, PASSWORD)
    else:
        response = await client.post(path)
        command = (
            Types.LogoutCommand("original-refresh", "original-access")
            if name == "logout_session"
            else Types.TokenCommand("original-access")
        )
    assert response.status_code == 204 and response.content == b""
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 4 and all("Max-Age=0" in cookie for cookie in cookies)
    http_backend.operations[name].assert_awaited_once_with(command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,status,code",
    [
        ("missing_origin", 403, "origin_forbidden"),
        ("wrong_origin", 403, "origin_forbidden"),
        ("missing_header", 403, "csrf_failed"),
        ("missing_cookie", 403, "csrf_failed"),
        ("invalid_signed_token", 403, "csrf_failed"),
        ("wrong_token_kind", 403, "csrf_failed"),
    ],
)
async def test_csrf_origin_failures_stop_route_before_login(
    http_backend: HTTPBackend,
    client: AsyncClient,
    change: str,
    status: int,
    code: str,
) -> None:
    if change == "missing_origin":
        del client.headers["Origin"]
    elif change == "wrong_origin":
        client.headers["Origin"] = "https://other.example"
    elif change == "missing_header":
        del client.headers["X-CSRF-Token"]
    elif change == "missing_cookie":
        client.cookies.clear()
    else:
        client.cookies.clear()
        token = (
            http_backend.backend.login.access_token
            if change == "wrong_token_kind"
            else "invalid-jwt"
        )
        client.cookies.set(
            http_backend.backend.auth.settings.cookie_name("csrf"), token
        )
        client.headers["X-CSRF-Token"] = token
    response = await client.post(
        "/auth/login", json={"email": "person@example.com", "password": PASSWORD}
    )
    assert response.status_code == status
    assert response.json() == {"error": {"code": code}}
    http_backend.operations["login_user"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"email": "person@example.com", "password": "private-short"[:11]},
        {"email": "person@example.com", "password": PASSWORD, "private-extra": TOKEN},
    ],
)
async def test_validation_error_does_not_reflect_password_or_extra_input(
    http_backend: HTTPBackend,
    client: AsyncClient,
    body: dict[str, str],
) -> None:
    response = await client.post("/auth/login", json=body)
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_input"}}
    assert "private" not in response.text
    http_backend.operations["login_user"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,method,status",
    [
        ("access", "POST", 403),
        ("refresh", "POST", 403),
        ("", "POST", 200),
        ("access", "GET", 200),
    ],
)
async def test_middleware_protects_cookie_writes_outside_auth_router(
    http_backend: HTTPBackend,
    client: AsyncClient,
    kind: str,
    method: str,
    status: int,
) -> None:
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token")
    if kind:
        client.cookies.set(
            http_backend.backend.auth.settings.cookie_name(kind), "cookie-value"
        )
    response = await client.request(method, "/outside-auth")
    assert response.status_code == status
    assert response.json() == (
        {"error": {"code": "csrf_failed"}} if status == 403 else {"ok": True}
    )


@pytest.mark.asyncio
async def test_google_start_and_callback_use_flow_cookie_and_keep_303_redirect(
    http_backend: HTTPBackend,
    client: AsyncClient,
) -> None:
    item = http_backend
    started = await client.post("/auth/google/start", json={"redirect": "/account"})
    assert started.status_code == 200
    assert started.json() == {
        "authorization_url": "https://accounts.google.com/example"
    }
    assert "Max-Age=600" in started.headers["set-cookie"]
    assert "private-flow" not in started.text
    item.operations["start_google_login"].assert_awaited_once_with(
        Types.GoogleStartCommand("/account")
    )
    response = await client.get(
        "/auth/google/callback",
        params={"state": "private-state", "code": "private-code"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/account?tab=security"
    assert response.content == b""
    item.operations["complete_google_login"].assert_awaited_once_with(
        Types.GoogleCallbackCommand("private-state", "private-code", "private-flow")
    )
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 3 and "Max-Age=0" in cookies[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [True, False])
async def test_google_callback_failure_clears_only_flow_and_hides_inputs(
    http_backend: HTTPBackend,
    client: AsyncClient,
    missing: bool,
) -> None:
    operation = http_backend.operations["complete_google_login"]
    operation.side_effect = Types.AuthError("invalid_google_login")
    params = {} if missing else {"state": "private-state", "code": "private-code"}
    response = await client.get("/auth/google/callback", params=params)
    assert response.status_code == 400
    assert response.json() == {"error": {"code": "invalid_google_login"}}
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1 and "flow=" in cookies[0] and "Max-Age=0" in cookies[0]
    if missing:
        operation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_verified_dependency_returns_only_service_verified_uuid(
    http_backend: HTTPBackend,
    client: AsyncClient,
    method: str,
) -> None:
    settings = http_backend.backend.auth.settings
    client.cookies.set(settings.cookie_name("access"), "original-access")
    response = await client.request(method, "/verified-identity")
    assert response.status_code == 200
    assert response.json() == {"id": str(http_backend.backend.user.id)}
    http_backend.operations["get_authenticated_user"].assert_awaited_once_with(
        Types.TokenCommand("original-access")
    )


@pytest.mark.asyncio
async def test_rate_failure_and_unconfigured_service_keep_safe_http_errors(
    http_backend: HTTPBackend,
    client: AsyncClient,
) -> None:
    http_backend.operations["check_rate_limit"].side_effect = Types.AuthError(
        "rate_limited"
    )
    response = await client.get("/auth/me")
    assert response.status_code == 429 and response.headers["Retry-After"] == "900"
    assert response.json() == {"error": {"code": "rate_limited"}}
    http_backend.operations["get_authenticated_user"].assert_not_awaited()
    del http_backend.app.state.authentication
    response = await client.get("/auth/csrf")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "auth_not_configured"}}
    # Middleware remains optional when authentication is absent.
    client.cookies.set("__Host-chatkit_access", "old-cookie")
    assert (await client.post("/outside-auth")).status_code == 200
