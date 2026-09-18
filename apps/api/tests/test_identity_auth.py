"""실제 PostgreSQL과 HTTP 쿠키를 이용하는 인증 통합·동시성 검사. 외부 메일/Google만 대역 사용."""

import asyncio
import multiprocessing
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import pytest_asyncio
from app.db.base import Base
from app.db.models.identity import (
    AuthActionToken,
    AuthOAuthAttempt,
    AuthRateLimit,
    AuthSession,
    User,
    UserOAuthAccount,
)
from app.main import create_app
from app.modules.identity import types as Types
from app.modules.identity.dependencies import get_verified_user_id
from app.modules.identity.security import token_hash
from app.modules.identity.service import AuthenticationService, GoogleLoginService
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_identity_security import auth_settings  # noqa: F401 - 공통 임시 설정 fixture

PASSWORD = "길고 안전한 password 123!"
EMAIL = "person@example.com"
AUTH_TABLES = [
    User.__table__,
    UserOAuthAccount.__table__,
    AuthSession.__table__,
    AuthActionToken.__table__,
    AuthOAuthAttempt.__table__,
    AuthRateLimit.__table__,
]


class RecordingMailer:
    def __init__(self):
        self.messages = []

    async def send_mail(self, recipient, purpose, link):
        self.messages.append((recipient, purpose, link))

    def token(self, purpose):
        return next(
            link.split("#token=", 1)[1]
            for _, p, link in reversed(self.messages)
            if p == purpose
        )


class FakeGoogleVerifier:
    def __init__(self):
        self.identity = Types.GoogleIdentityInfo("google-123", "google@example.com")
        self.calls = []

    async def verify_code(self, code, verifier, nonce):
        self.calls.append((code, verifier, nonce))
        if code != "valid-code":
            raise Types.AuthError("invalid_google_login")
        return self.identity


@pytest_asyncio.fixture
async def identity_db():
    # 인증은 vector 확장에 의존하지 않으므로 독립 PostgreSQL에서도 검증 가능하다.
    url = os.getenv("TEST_AUTH_DATABASE_URL") or os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_AUTH_DATABASE_URL or TEST_DATABASE_URL required")
    if "test" not in url.rsplit("/", 1)[-1]:
        raise RuntimeError("Test database name must include test")
    schema = "auth_test_" + uuid4().hex
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=AUTH_TABLES, checkfirst=False
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await engine.dispose()


@pytest_asyncio.fixture
async def auth_http(identity_db, auth_settings):  # noqa: F811 - pytest 재사용 fixture
    app = create_app()
    mailer, google = RecordingMailer(), FakeGoogleVerifier()
    auth = AuthenticationService(identity_db, auth_settings, mailer)
    app.state.authentication = auth
    app.state.google_login = GoogleLoginService(auth, google)

    @app.get("/verified-identity")
    async def verified(user_id: Annotated[str, Depends(get_verified_user_id)]):
        return {"id": str(user_id)}

    @app.post("/verified-identity")
    async def verified_write(user_id: Annotated[str, Depends(get_verified_user_id)]):
        return {"id": str(user_id)}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        await csrf(client)
        yield client, auth, mailer, google, app


async def csrf(client):
    response = await client.get("/auth/csrf")
    assert response.status_code == 200
    client.headers.update(
        {"Origin": "https://testserver", "X-CSRF-Token": response.json()["csrf_token"]}
    )


async def register_verified(client, mailer, email=EMAIL):
    response = await client.post(
        "/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 202, response.text
    response = await client.post(
        "/auth/email/verify", json={"token": mailer.token("verify")}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def login(client, email=EMAIL, password=PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


@pytest.mark.asyncio
async def test_register_verify_login_refresh_logout_http(auth_http):
    client, auth, mailer, _, _ = auth_http
    assert (
        await client.post(
            "/auth/register",
            json={"email": " Person@Example.com ", "password": PASSWORD},
        )
    ).status_code == 202
    assert (await login(client)).status_code == 401
    assert not client.cookies.get(auth.settings.cookie_name("access"))
    token = mailer.token("verify")
    assert (await client.post("/auth/email/verify", json={"token": token})).json()[
        "email_verified"
    ] is True
    response = await login(client)
    assert response.status_code == 200
    assert set(response.json()) == {"id", "email", "email_verified"}
    for cookie in response.headers.get_list("set-cookie"):
        assert (
            "HttpOnly" in cookie
            and "Secure" in cookie
            and "SameSite=lax" in cookie
            and "Domain=" not in cookie
        )
    access = client.cookies[auth.settings.cookie_name("access")]
    refresh = client.cookies[auth.settings.cookie_name("refresh")]
    assert (await client.get("/auth/me")).json()["email"] == EMAIL
    assert (await client.get("/verified-identity")).json()["id"] == response.json()[
        "id"
    ]
    assert (await client.post("/auth/refresh")).status_code == 200
    assert client.cookies[auth.settings.cookie_name("refresh")] != refresh
    assert (await client.post("/auth/logout")).status_code == 204
    assert auth.settings.cookie_name("access") not in client.cookies
    with pytest.raises(Types.AuthError):
        await auth.get_authenticated_user(Types.TokenCommand(access))


@pytest.mark.asyncio
async def test_reset_revokes_every_session_and_is_single_use(auth_http):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    first = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    second = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    assert (
        await client.post("/auth/password/reset/request", json={"email": EMAIL})
    ).status_code == 202
    token = mailer.token("reset")
    new_password = "새 비밀번호 password 456!"
    response = await client.post(
        "/auth/password/reset", json={"token": token, "password": new_password}
    )
    assert response.status_code == 204
    for issued in (first, second):
        with pytest.raises(Types.AuthError):
            await auth.get_authenticated_user(Types.TokenCommand(issued.access_token))
        with pytest.raises(Types.AuthError):
            await auth.refresh_session(Types.TokenCommand(issued.refresh_token))
    await csrf(client)
    assert (
        await client.post(
            "/auth/password/reset", json={"token": token, "password": new_password}
        )
    ).status_code == 400
    assert (await login(client)).status_code == 401
    assert (await login(client, password=new_password)).status_code == 200


@pytest.mark.asyncio
async def test_refresh_reuse_concurrency_and_lost_response_revoke_family(auth_http):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    original = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    results = await asyncio.gather(
        *(
            auth.refresh_session(Types.TokenCommand(original.refresh_token))
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    successes = [x for x in results if isinstance(x, Types.LoginInfo)]
    assert len(successes) == 1
    assert any(
        isinstance(x, Types.AuthError) and x.code == "refresh_reused" for x in results
    )
    with pytest.raises(Types.AuthError):
        await auth.get_authenticated_user(Types.TokenCommand(successes[0].access_token))
    # 응답 유실도 같은 정책이다. 첫 갱신의 새 토큰을 잃고 이전 토큰을 재전송하면 폐기한다.
    original = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    lost = await auth.refresh_session(Types.TokenCommand(original.refresh_token))
    with pytest.raises(Types.AuthError, match="refresh_reused"):
        await auth.refresh_session(Types.TokenCommand(original.refresh_token))
    with pytest.raises(Types.AuthError):
        await auth.refresh_session(Types.TokenCommand(lost.refresh_token))


@pytest.mark.asyncio
async def test_all_logout_and_absolute_expiry(auth_http, identity_db):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    await login(client)
    first = client.cookies[auth.settings.cookie_name("access")]
    second = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    rotated = await auth.refresh_session(Types.TokenCommand(second.refresh_token))
    assert rotated.expires_at == second.expires_at
    assert (second.expires_at - datetime.now(UTC)).total_seconds() <= 14 * 86400
    assert (await client.post("/auth/logout-all")).status_code == 204
    for token in (first, second.access_token):
        with pytest.raises(Types.AuthError):
            await auth.get_authenticated_user(Types.TokenCommand(token))
    third = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    async with identity_db.begin() as session:
        await session.execute(
            update(AuthSession).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    with pytest.raises(Types.AuthError):
        await auth.get_authenticated_user(Types.TokenCommand(third.access_token))


@pytest.mark.asyncio
async def test_duplicate_registration_and_action_token_races(auth_http, identity_db):
    client, auth, mailer, _, _ = auth_http
    responses = await asyncio.gather(
        *(
            client.post(
                "/auth/register",
                json={"email": EMAIL.upper() if i else EMAIL, "password": PASSWORD},
            )
            for i in range(2)
        )
    )
    assert [x.status_code for x in responses] == [202, 202]
    async with identity_db() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
    token = mailer.token("verify")
    responses = await asyncio.gather(
        *(client.post("/auth/email/verify", json={"token": token}) for _ in range(2))
    )
    assert sorted(x.status_code for x in responses) == [200, 400]
    await auth.request_password_reset(Types.EmailCommand(EMAIL))
    command = Types.ResetPasswordCommand(mailer.token("reset"), PASSWORD + "2")
    results = await asyncio.gather(
        auth.reset_password(command),
        auth.reset_password(command),
        return_exceptions=True,
    )
    assert sum(x is None for x in results) == 1
    assert sum(isinstance(x, Types.AuthError) for x in results) == 1


@pytest.mark.asyncio
async def test_resend_expiry_cleanup_and_no_raw_token_storage(auth_http, identity_db):
    client, auth, mailer, _, _ = auth_http
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    old = mailer.token("verify")
    assert (
        await client.post("/auth/email/resend", json={"email": EMAIL})
    ).status_code == 202
    new = mailer.token("verify")
    assert new != old
    assert (
        await client.post("/auth/email/verify", json={"token": old})
    ).status_code == 400
    async with identity_db.begin() as session:
        rows = (await session.scalars(select(AuthActionToken))).all()
        assert {x.token_hash for x in rows} == {token_hash(old), token_hash(new)}
        user = await session.scalar(select(User))
        assert (
            user.password_hash.startswith("$argon2id$")
            and PASSWORD not in user.password_hash
        )
        await session.execute(
            update(AuthActionToken).values(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert (
        await client.post("/auth/email/verify", json={"token": new})
    ).status_code == 400
    async with identity_db.begin() as session:
        await session.execute(
            update(User).values(
                pending_expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    result = await auth.cleanup_expired_auth()
    assert result.users == 1
    async with identity_db() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.asyncio
async def test_csrf_origin_validation_sensitive_response_and_rate_limits(
    auth_http, caplog
):
    client, _auth, _mailer, _, _ = auth_http
    body = {"email": EMAIL, "password": PASSWORD}
    assert (
        await client.post(
            "/auth/register", json=body, headers={"Origin": "https://evil.test"}
        )
    ).status_code == 403
    assert (
        await client.post(
            "/auth/register", json=body, headers={"X-CSRF-Token": "forged"}
        )
    ).status_code == 403
    token = client.headers.pop("x-csrf-token")
    assert (await client.post("/auth/register", json=body)).status_code == 403
    client.headers["X-CSRF-Token"] = token
    response = await client.post(
        "/auth/register", json={**body, "unexpected_secret": "private"}
    )
    assert (
        response.status_code == 422
        and PASSWORD not in response.text
        and "private" not in response.text
    )
    for _ in range(5):
        assert (
            await client.post("/auth/password/reset/request", json={"email": EMAIL})
        ).status_code == 202
    assert (
        await client.post("/auth/password/reset/request", json={"email": EMAIL})
    ).status_code == 429
    assert PASSWORD not in caplog.text
    assert EMAIL not in caplog.text


@pytest.mark.asyncio
async def test_rate_limit_is_shared_by_independent_service_instances(
    auth_http, identity_db
):
    _, auth, mailer, _, _ = auth_http
    other = AuthenticationService(identity_db, auth.settings, mailer)
    command = Types.RateLimitCommand("parallel-test", "same-actor", 3, 300)
    results = await asyncio.gather(
        *(service.check_rate_limit(command) for service in [auth, other] * 5),
        return_exceptions=True,
    )
    assert sum(x is None for x in results) == 3
    assert (
        sum(
            isinstance(x, Types.AuthError) and x.code == "rate_limited" for x in results
        )
        == 7
    )


async def google_start(client):
    response = await client.post("/auth/google/start", json={"redirect": "/account"})
    assert response.status_code == 200, response.text
    return parse_qs(urlsplit(response.json()["authorization_url"]).query)


@pytest.mark.asyncio
async def test_google_http_flow_minimal_scope_sub_identity_and_no_password_reset(
    auth_http, identity_db
):
    client, auth, mailer, google, _ = auth_http
    query = await google_start(client)
    assert query["scope"] == ["openid email"] and query["code_challenge_method"] == [
        "S256"
    ]
    assert query["redirect_uri"] == [auth.settings.google_callback_url]
    response = await client.get(
        "/auth/google/callback",
        params={"state": query["state"][0], "code": "valid-code"},
    )
    assert response.status_code == 303 and response.headers["location"] == "/account"
    first = (await client.get("/auth/me")).json()
    assert google.calls[0][2] == query["nonce"][0]
    import base64
    import hashlib

    assert (
        base64.urlsafe_b64encode(hashlib.sha256(google.calls[0][1].encode()).digest())
        .rstrip(b"=")
        .decode()
        == query["code_challenge"][0]
    )
    assert (
        await client.post(
            "/auth/password/reset/request", json={"email": "google@example.com"}
        )
    ).status_code == 202
    assert not mailer.messages
    async with identity_db() as session:
        assert (await session.scalar(select(User))).password_hash is None
        account = await session.scalar(select(UserOAuthAccount))
        assert (account.provider, account.provider_user_id) == ("google", "google-123")
    google.identity = Types.GoogleIdentityInfo("google-123", "changed@example.com")
    query = await google_start(client)
    assert (
        await client.get(
            "/auth/google/callback",
            params={"state": query["state"][0], "code": "valid-code"},
        )
    ).status_code == 303
    assert (await client.get("/auth/me")).json() == first


@pytest.mark.asyncio
async def test_google_conflict_state_replay_and_redirect_rejection(auth_http):
    client, auth, mailer, google, _ = auth_http
    await register_verified(client, mailer)
    for redirect in ("//evil.test", "https://evil.test", "/%2f/evil.test"):
        assert (
            await client.post("/auth/google/start", json={"redirect": redirect})
        ).status_code == 400
    google.identity = Types.GoogleIdentityInfo("different-sub", EMAIL)
    query = await google_start(client)
    cookie = client.cookies.get(auth.settings.cookie_name("flow"))
    assert (
        await client.get(
            "/auth/google/callback", params={"state": "wrong", "code": "valid-code"}
        )
    ).status_code == 400
    assert not google.calls
    client.cookies.set(auth.settings.cookie_name("flow"), cookie)
    params = {"state": query["state"][0], "code": "valid-code"}
    assert (await client.get("/auth/google/callback", params=params)).status_code == 409
    client.cookies.set(auth.settings.cookie_name("flow"), cookie)
    assert (await client.get("/auth/google/callback", params=params)).status_code == 400
    assert len(google.calls) == 1


@pytest.mark.asyncio
async def test_unknown_unverified_google_and_wrong_password_responses_match(auth_http):
    client, _auth, _mailer, _, _ = auth_http
    missing = await login(client)
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    pending = await login(client)
    assert (
        missing.status_code == pending.status_code == 401
        and missing.json() == pending.json()
    )
    responses = [
        await client.post("/auth/password/reset/request", json={"email": email})
        for email in [EMAIL, "unknown@example.com"]
    ]
    assert responses[0].json() == responses[1].json()


@pytest.mark.asyncio
async def test_cookie_auth_protects_other_routes_and_cors(auth_http):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    await login(client)
    assert (await client.post("/verified-identity")).status_code == 200
    assert (
        await client.post("/verified-identity", headers={"Origin": "https://evil.test"})
    ).status_code == 403
    client.headers.pop("Origin")
    assert (await client.post("/verified-identity")).status_code == 403
    forbidden = await client.options(
        "/auth/login",
        headers={
            "Origin": "https://evil.test",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert (
        forbidden.status_code == 400
        and "access-control-allow-origin" not in forbidden.headers
    )
    # 조립 시 허용 origin 설정은 환경에서 읽는다. 기본 API origin만 허용된다.
    allowed = await client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert (
        allowed.status_code == 200
        and allowed.headers["access-control-allow-origin"] == "http://localhost:8000"
    )
    assert allowed.headers["access-control-allow-credentials"] == "true"
    await csrf(client)
    client.cookies.delete(auth.settings.cookie_name("refresh"))
    access = client.cookies[auth.settings.cookie_name("access")]
    assert (await client.post("/auth/logout")).status_code == 204
    with pytest.raises(Types.AuthError):
        await auth.get_authenticated_user(Types.TokenCommand(access))


@pytest.mark.asyncio
async def test_tampered_and_wrong_type_cookies_fail_at_http_boundary(auth_http):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    issued = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    for token in (
        issued.refresh_token,
        issued.access_token[:-10] + "tamperedAA",
        "not-a-jwt",
    ):
        client.cookies.set(
            auth.settings.cookie_name("access"),
            token,
            domain="testserver.local",
            path="/",
        )
        response = await client.get("/auth/me")
        assert response.status_code == 401 and token not in response.text
        assert "Max-Age=0" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_suspended_user_and_google_only_reset_token_are_rejected(
    auth_http, identity_db
):
    client, auth, mailer, _, _ = auth_http
    await register_verified(client, mailer)
    issued = await auth.login_user(Types.CredentialsCommand(EMAIL, PASSWORD))
    await auth.request_password_reset(Types.EmailCommand(EMAIL))
    reset = mailer.token("reset")
    async with identity_db.begin() as session:
        await session.execute(update(User).values(status="suspended"))
    with pytest.raises(Types.AuthError):
        await auth.get_authenticated_user(Types.TokenCommand(issued.access_token))
    with pytest.raises(Types.AuthError):
        await auth.refresh_session(Types.TokenCommand(issued.refresh_token))
    async with identity_db.begin() as session:
        await session.execute(update(User).values(status="active", password_hash=None))
    with pytest.raises(Types.AuthError):
        await auth.reset_password(Types.ResetPasswordCommand(reset, PASSWORD + "new"))


def _check_rate_in_process(url, schema, settings, queue):
    # 각 자식 프로세스는 독립 엔진·서비스를 사용한다. 제한 상태를 메모리로 공유하지 않는다.
    async def check():
        engine = create_async_engine(
            url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
        )
        service = AuthenticationService(
            async_sessionmaker(engine), settings, RecordingMailer()
        )
        results = []
        try:
            for _ in range(2):
                try:
                    await service.check_rate_limit(
                        Types.RateLimitCommand("process-test", "same-user", 3, 3600)
                    )
                    results.append("allowed")
                except Types.AuthError as error:
                    results.append(error.code)
            queue.put(results)
        finally:
            await engine.dispose()

    asyncio.run(check())


@pytest.mark.asyncio
async def test_rate_limit_across_real_processes(auth_http, identity_db):
    _, auth, _, _, _ = auth_http
    async with identity_db() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    # 테스트 DB URL도 패스워드 마스킹 문자열로 바꾸지 않고 원래 설정을 사용한다.
    url = os.getenv("TEST_AUTH_DATABASE_URL") or os.environ["TEST_DATABASE_URL"]

    def run_processes():
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        workers = [
            context.Process(
                target=_check_rate_in_process, args=(url, schema, auth.settings, queue)
            )
            for _ in range(4)
        ]
        try:
            for worker in workers:
                worker.start()
            results = [item for _ in workers for item in queue.get(timeout=30)]
            for worker in workers:
                worker.join(timeout=10)
                assert worker.exitcode == 0
            return results
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
            queue.close()

    results = await asyncio.to_thread(run_processes)
    assert results.count("allowed") == 3 and results.count("rate_limited") == 5
