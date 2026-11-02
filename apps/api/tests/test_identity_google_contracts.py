"""Offline Google workflow/SMTP contracts; no provider or database connections."""

import base64
import hashlib
import json
import smtplib
import ssl
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from test_identity_auth_contracts import Backend
from test_identity_auth_contracts import backend as backend_fixture
from test_identity_security import auth_settings as auth_settings_fixture

from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.adapters import GoogleOIDCVerifier, SMTPMailSender
from app.modules.identity.service.workflow.google import GoogleLoginService
from app.modules.identity.settings import AuthSettings

auth_settings = auth_settings_fixture
backend = backend_fixture


class RecordingVerifier:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[str, str, str]] = []
        self.failure: Types.AuthError | None = None

    async def verify_code(
        self, code: str, verifier: str, nonce: str
    ) -> Types.GoogleIdentityInfo:
        assert self.events[-1] == "commit"
        self.events.append("verify")
        self.calls.append((code, verifier, nonce))
        if self.failure is not None:
            raise self.failure
        return Types.GoogleIdentityInfo("provider-sub", "changed@example.com")


@dataclass
class GoogleBackend:
    backend: Backend
    workflow: GoogleLoginService
    verifier: RecordingVerifier
    create_state: AsyncMock
    consume_state: AsyncMock
    lookup: AsyncMock


@pytest.fixture
def google_backend(backend: Backend, monkeypatch: pytest.MonkeyPatch) -> GoogleBackend:
    item = backend
    consumed = False

    async def consume(
        session: AsyncSession, state_hash: str, now: datetime
    ) -> str | None:
        nonlocal consumed
        assert session.in_transaction()
        item.events.append("consume")
        if consumed:
            return None
        consumed = True
        return state_hash

    async def lock(session: AsyncSession, identity: str) -> None:
        item.events.append("lock:" + identity)

    async def issue(*args: object, **kwargs: object) -> None:
        item.events.append("issue")

    create_state = AsyncMock()
    consume_state = AsyncMock(side_effect=consume)
    lookup = AsyncMock(return_value=item.user)
    monkeypatch.setattr(Repository, "create_oauth_attempt", create_state)
    monkeypatch.setattr(Repository, "consume_oauth_attempt", consume_state)
    monkeypatch.setattr(Repository, "get_google_user", lookup)
    monkeypatch.setattr(Repository, "create_google_account", AsyncMock())
    item.operations["lock_identity"].side_effect = lock
    item.operations["create_session"].side_effect = issue
    verifier = RecordingVerifier(item.events)
    return GoogleBackend(
        item,
        GoogleLoginService(item.auth, verifier),
        verifier,
        create_state,
        consume_state,
        lookup,
    )


async def start_callback(item: GoogleBackend) -> Types.GoogleCallbackCommand:
    started = await item.workflow.start_google_login(
        Types.GoogleStartCommand("/account?tab=security")
    )
    state = parse_qs(urlsplit(started.url).query)["state"][0]
    item.backend.events.clear()
    return Types.GoogleCallbackCommand(state, "temporary-code", started.cookie)


@pytest.mark.asyncio
async def test_start_preserves_minimal_scope_pkce_and_hashed_state(
    google_backend: GoogleBackend,
) -> None:
    item = google_backend
    before = datetime.now(UTC)
    started = await item.workflow.start_google_login(
        Types.GoogleStartCommand("/account")
    )
    query = parse_qs(urlsplit(started.url).query)
    flow = json.loads(item.workflow.fernet.decrypt(started.cookie.encode(), ttl=600))
    assert query["scope"] == ["openid email"]
    assert query["redirect_uri"] == [item.backend.auth.settings.google_callback_url]
    assert query["state"] == [flow["state"]]
    assert query["nonce"] == [flow["nonce"]]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(flow["verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert query["code_challenge"] == [challenge]
    assert query["code_challenge_method"] == ["S256"]
    saved = item.create_state.await_args
    assert saved is not None
    assert saved.args[1] == Security.token_hash(flow["state"])
    assert (
        before + timedelta(minutes=10)
        <= saved.args[2]
        <= (datetime.now(UTC) + timedelta(minutes=10))
    )
    assert flow["verifier"] not in started.url
    assert started.cookie not in repr(started) and started.url not in repr(started)
    assert item.backend.events == ["commit"]


@pytest.mark.asyncio
async def test_callback_commits_state_before_verify_and_uses_existing_sub(
    google_backend: GoogleBackend,
) -> None:
    item = google_backend
    command = await start_callback(item)
    result = await item.workflow.complete_google_login(command)
    assert result.login.user.id == item.backend.user.id
    assert result.login.user.email == item.backend.user.email
    assert result.redirect == "/account?tab=security"
    assert item.backend.events == [
        "consume",
        "commit",
        "verify",
        "lock:google:provider-sub",
        "lock:email:changed@example.com",
        "issue",
        "commit",
    ]
    flow = json.loads(item.workflow.fernet.decrypt(command.cookie.encode()))
    assert item.verifier.calls == [(command.code, flow["verifier"], flow["nonce"])]
    item.backend.operations["get_user_by_email"].assert_not_awaited()
    item.backend.operations["create_user"].assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_keeps_state_consumed_and_replay_never_verifies(
    google_backend: GoogleBackend,
) -> None:
    item = google_backend
    command = await start_callback(item)
    item.verifier.failure = Types.AuthError("invalid_google_login")
    for _ in range(2):
        with pytest.raises(Types.AuthError, match="invalid_google_login"):
            await item.workflow.complete_google_login(command)
    assert item.backend.events == ["consume", "commit", "verify", "consume", "rollback"]
    assert len(item.verifier.calls) == 1
    item.lookup.assert_not_awaited()
    item.backend.operations["create_session"].assert_not_awaited()


@pytest.mark.asyncio
async def test_session_failure_rolls_back_link_scope_after_state_commit(
    google_backend: GoogleBackend,
) -> None:
    item = google_backend
    command = await start_callback(item)
    item.backend.operations["create_session"].side_effect = RuntimeError("write failed")
    with pytest.raises(RuntimeError, match="write failed"):
        await item.workflow.complete_google_login(command)
    assert item.backend.events[:3] == ["consume", "commit", "verify"]
    assert item.backend.events[-1] == "rollback"
    assert item.backend.events.count("commit") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["signature", "state", "shape", "redirect", "expired"]
)
async def test_bad_cookie_never_consumes_state_or_calls_provider(
    google_backend: GoogleBackend,
    change: str,
) -> None:
    item = google_backend
    command = await start_callback(item)
    flow = json.loads(item.workflow.fernet.decrypt(command.cookie.encode()))
    if change == "signature":
        cookie = "invalid-cookie"
    elif change == "expired":
        cookie = item.workflow.fernet.encrypt_at_time(
            json.dumps(flow).encode(), int(datetime.now(UTC).timestamp()) - 601
        ).decode()
    else:
        if change == "state":
            flow["state"] = "other"
        elif change == "shape":
            flow = []
        else:
            flow["redirect"] = "https://other.example/"
        cookie = item.workflow.fernet.encrypt(json.dumps(flow).encode()).decode()
    with pytest.raises(Types.AuthError):
        await item.workflow.complete_google_login(replace(command, cookie=cookie))
    item.consume_state.assert_not_awaited()
    assert not item.verifier.calls
    assert item.backend.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("condition", ["conflict", "inactive", "unverified"])
async def test_account_conflicts_and_inactive_identity_do_not_issue_session(
    google_backend: GoogleBackend,
    condition: str,
) -> None:
    item = google_backend
    command = await start_callback(item)
    if condition == "conflict":
        item.lookup.return_value = None
        error = "account_conflict"
    else:
        if condition == "inactive":
            item.backend.user.status = "suspended"
        else:
            item.backend.user.email_verified = False
        error = "invalid_google_login"
    with pytest.raises(Types.AuthError, match=error):
        await item.workflow.complete_google_login(command)
    assert item.backend.events[-1] == "rollback"
    item.backend.operations["create_session"].assert_not_awaited()
    item.backend.operations["create_user"].assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tls", ["none", "starttls", "ssl"])
@pytest.mark.parametrize("authenticated", [False, True])
async def test_smtp_transport_auth_message_and_context_exit(
    auth_settings: AuthSettings,
    monkeypatch: pytest.MonkeyPatch,
    tls: str,
    authenticated: bool,
) -> None:
    settings = replace(
        auth_settings,
        smtp_tls=tls,
        smtp_user="user" if authenticated else "",
        smtp_password="secret" if authenticated else "",
    )
    smtp = MagicMock(spec=smtplib.SMTP)
    smtp.__enter__.return_value = smtp
    plain, secure = MagicMock(return_value=smtp), MagicMock(return_value=smtp)
    monkeypatch.setattr(smtplib, "SMTP", plain)
    monkeypatch.setattr(smtplib, "SMTP_SSL", secure)
    await SMTPMailSender(settings).send_mail(
        "person@example.com", "verify", "https://testserver/#private-token"
    )
    constructor = secure if tls == "ssl" else plain
    assert constructor.call_args.args == (settings.smtp_host, settings.smtp_port)
    assert constructor.call_args.kwargs["timeout"] == 10
    if tls == "ssl":
        assert isinstance(constructor.call_args.kwargs["context"], ssl.SSLContext)
        plain.assert_not_called()
    else:
        assert "context" not in constructor.call_args.kwargs
        secure.assert_not_called()
    assert smtp.starttls.call_count == int(tls == "starttls")
    if authenticated:
        smtp.login.assert_called_once_with("user", "secret")
    else:
        smtp.login.assert_not_called()
    message = smtp.send_message.call_args.args[0]
    assert str(message["Subject"]) == "이메일 인증"
    assert str(message["To"]) == "person@example.com"
    assert "#private-token" in message.get_content()
    smtp.__exit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("unexpected", [False, True])
async def test_smtp_failure_closes_transport_and_preserves_error_boundary(
    auth_settings: AuthSettings,
    monkeypatch: pytest.MonkeyPatch,
    unexpected: bool,
) -> None:
    smtp = MagicMock(spec=smtplib.SMTP)
    smtp.__enter__.return_value = smtp
    smtp.__exit__.return_value = False
    failure = (
        RuntimeError("implementation failure")
        if unexpected
        else (smtplib.SMTPDataError(451, b"try later"))
    )
    smtp.send_message.side_effect = failure
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=smtp))
    with pytest.raises(RuntimeError if unexpected else Types.AuthError) as caught:
        await SMTPMailSender(auth_settings).send_mail(
            "person@example.com", "reset", "https://testserver/#private-token"
        )
    assert (
        (caught.value is failure) if unexpected else (caught.value.__cause__ is failure)
    )
    smtp.__exit__.assert_called_once()


@pytest.mark.asyncio
async def test_token_exchange_fixed_request_and_close_before_id_token_verification(
    auth_settings: AuthSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id_token": "original-token", "extra": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "AsyncClient", MagicMock(return_value=client))
    verifier = GoogleOIDCVerifier(auth_settings)

    def verify(token: str, nonce: str) -> Types.GoogleIdentityInfo:
        assert client.is_closed
        assert (token, nonce) == ("original-token", "expected-nonce")
        return Types.GoogleIdentityInfo("sub", "person@example.com")

    monkeypatch.setattr(verifier, "verify_id_token", verify)
    result = await verifier.verify_code(
        "temporary-code", "pkce-value", "expected-nonce"
    )
    assert result.sub == "sub"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://oauth2.googleapis.com/token"
    assert request.method == "POST"
    assert parse_qs(request.content.decode()) == {
        "grant_type": ["authorization_code"],
        "code": ["temporary-code"],
        "code_verifier": ["pkce-value"],
        "client_id": [auth_settings.google_client_id],
        "client_secret": [auth_settings.google_client_secret],
        "redirect_uri": [auth_settings.google_callback_url],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, None, [], {"id_token": None}, {"id_token": ""}])
async def test_malformed_provider_response_is_rejected_and_http_client_closed(
    auth_settings: AuthSettings,
    monkeypatch: pytest.MonkeyPatch,
    body: object,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=json.dumps(body), headers={"Content-Type": "application/json"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "AsyncClient", MagicMock(return_value=client))
    verifier = GoogleOIDCVerifier(auth_settings)
    # Every body fails before key lookup; protect this offline contract explicitly.
    keys = MagicMock(side_effect=AssertionError("unexpected key network lookup"))
    monkeypatch.setattr(verifier.keys, "fetch_data", keys)
    with pytest.raises(Types.AuthError, match="invalid_google_login"):
        await verifier.verify_code("temporary-code", "pkce-value", "nonce")
    assert client.is_closed
    keys.assert_not_called()
