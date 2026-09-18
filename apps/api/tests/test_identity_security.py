"""DB 없이 실행하는 암호·OIDC 검증 경계 테스트. 키와 증명은 실행마다 임시 생성한다."""

import base64
import logging
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from app.modules.identity.adapters import GoogleOIDCVerifier, SMTPMailSender
from app.modules.identity.http_security import AuthAccessLogFilter
from app.modules.identity.security import (
    PASSWORD_HASHER,
    TokenCodec,
    normalize_email,
    safe_redirect,
    validate_password,
    verify_password,
)
from app.modules.identity.settings import AuthSettings
from app.modules.identity.types import AuthError, CredentialsCommand
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def auth_settings():
    return AuthSettings(
        jwt_key=base64.b64encode(secrets.token_bytes(32)).decode(),
        flow_key=Fernet.generate_key().decode(),
        environment="test",
        public_origin="https://testserver",
        allowed_origins=("https://testserver",),
        google_callback_url="https://testserver/auth/google/callback",
        google_client_id="test-client",
        google_client_secret="test-secret",
    )


def test_email_and_password_policy():
    assert normalize_email("  First.Last+tag@GMAIL.com ") == "first.last+tag@gmail.com"
    assert normalize_email("User@bücher.de") == "user@xn--bcher-kva.de"
    with pytest.raises(AuthError):
        normalize_email("성명@example.com")
    password = "비밀번호🔐 " * 16
    validate_password(password)
    encoded = PASSWORD_HASHER.hash(password)
    assert encoded.startswith("$argon2id$") and verify_password(password, encoded)
    assert not verify_password(password + "a", encoded)
    assert not verify_password(password, None)
    assert password not in repr(CredentialsCommand("user@example.com", password))
    for invalid in ("a" * 11, "a" * 129):
        with pytest.raises(AuthError):
            validate_password(invalid)


@pytest.mark.parametrize(
    "change",
    [
        "signature",
        "expired",
        "issuer",
        "audience",
        "type",
        "algorithm",
        "missing_exp",
        "missing_sid",
        "missing_jti",
        "sub",
        "iat",
    ],
)
def test_jwt_rejects_invalid_claims(auth_settings, change):
    codec = TokenCodec(auth_settings)
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": auth_settings.issuer,
        "aud": auth_settings.audience,
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "type": "access",
        "jti": "random",
        "iat": now,
        "nbf": now,
        "exp": now + 900,
    }
    key, algorithm = codec.key, "HS256"
    if change == "signature":
        key = secrets.token_bytes(32)
    elif change == "expired":
        claims["exp"] = now - 1
    elif change == "issuer":
        claims["iss"] = "other"
    elif change == "audience":
        claims["aud"] = "other"
    elif change == "type":
        claims["type"] = "refresh"
    elif change == "algorithm":
        algorithm = "HS384"
        key = secrets.token_bytes(48)
    elif change.startswith("missing_"):
        del claims[change.removeprefix("missing_")]
    elif change == "sub":
        claims["sub"] = "not-a-uuid"
    elif change == "iat":
        claims["iat"] = str(now)
    with pytest.raises(AuthError):
        codec.decode_token(jwt.encode(claims, key, algorithm=algorithm), "access")


def test_access_refresh_csrf_are_not_interchangeable(auth_settings):
    codec = TokenCodec(auth_settings)
    for kind in ("access", "refresh", "csrf"):
        token = codec.encode_token(
            kind=kind,
            subject=str(uuid4()),
            session_id=str(uuid4()),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        assert codec.decode_token(token, kind)["type"] == kind
        for wrong in {"access", "refresh", "csrf"} - {kind}:
            with pytest.raises(AuthError):
                codec.decode_token(token, wrong)


@pytest.mark.parametrize(
    "redirect",
    [
        "https://evil.test",
        "//evil.test",
        "/\\evil.test",
        "/%2f/evil.test",
        "/a\nb",
        "/a\tb",
        "javascript:alert(1)",
    ],
)
def test_redirect_rejects_browser_ambiguity(redirect):
    with pytest.raises(AuthError):
        safe_redirect(redirect)
    assert safe_redirect("/account?tab=security") == "/account?tab=security"


@pytest.mark.parametrize(
    "change",
    [
        None,
        "signature",
        "issuer",
        "audience",
        "nonce",
        "expired",
        "verified",
        "azp",
        "missing_sub",
    ],
)
def test_google_id_token_cryptographic_boundary(auth_settings, change):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = GoogleOIDCVerifier(auth_settings)
    verifier.keys = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    now = int(datetime.now(UTC).timestamp())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "test-client",
        "sub": "google-sub",
        "email": "google@example.com",
        "email_verified": True,
        "nonce": "expected-nonce",
        "iat": now,
        "exp": now + 300,
    }
    signing = private
    if change == "signature":
        signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif change == "issuer":
        claims["iss"] = "https://evil.test"
    elif change == "audience":
        claims["aud"] = "other-client"
    elif change == "nonce":
        claims["nonce"] = "wrong"
    elif change == "expired":
        claims["exp"] = now - 1
    elif change == "verified":
        claims["email_verified"] = "true"
    elif change == "azp":
        claims["azp"] = "other-client"
    elif change == "missing_sub":
        del claims["sub"]
    token = jwt.encode(claims, signing, algorithm="RS256", headers={"kid": "test"})
    if change is None:
        assert verifier.verify_id_token(token, "expected-nonce").sub == "google-sub"
    else:
        with pytest.raises(AuthError):
            verifier.verify_id_token(token, "expected-nonce")


def test_production_settings_fail_closed(auth_settings):
    with pytest.raises(ValueError):
        replace(auth_settings, environment="production")
    with pytest.raises(ValueError):
        replace(auth_settings, jwt_key="short")
    with pytest.raises(ValueError):
        replace(auth_settings, allowed_origins=("*",))
    with pytest.raises(ValueError):
        replace(auth_settings, google_callback_url="https://evil.test/callback")
    with pytest.raises(ValueError):
        replace(auth_settings, google_client_secret="")


def test_access_logs_remove_oauth_secrets():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "127.0.0.1",
            "GET",
            "/auth/google/callback?code=secret&state=secret",
            "1.1",
            303,
        ),
        None,
    )
    assert AuthAccessLogFilter().filter(record)
    assert "secret" not in record.getMessage()


@pytest.mark.asyncio
async def test_smtp_failure_is_explicit_and_does_not_log_link(
    auth_settings, monkeypatch, caplog
):
    def fail(*args, **kwargs):
        raise OSError("smtp unavailable")

    monkeypatch.setattr("smtplib.SMTP", fail)
    with pytest.raises(AuthError, match="mail_unavailable"):
        await SMTPMailSender(auth_settings).send_mail(
            "mail@example.com", "verify", "https://testserver/#secret"
        )
    assert "#secret" not in caplog.text
