"""검증된 라이브러리로 비밀번호·JWT·난수 증명을 처리하는 인증 내부 경계."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from uuid import UUID

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email

from app.modules.identity.types import AuthError

# Argon2id의 메모리 비용 64MiB를 명시한다. 불명 계정도 같은 검증 비용을 지불한다.
PASSWORD_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID
)
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def normalize_email(email: str) -> str:
    try:
        value = validate_email(
            email.strip(), check_deliverability=False, allow_smtputf8=False
        )
        return value.ascii_email.lower()
    except (EmailNotValidError, AttributeError) as exc:
        raise AuthError("invalid_input") from exc


def validate_password(password: str) -> None:
    # 문자 단위 12~128, UTF-8 최대 512바이트. 정규화·잘라내기 없이 공백과 유니코드를 보존한다.
    try:
        size = len(password.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise AuthError("invalid_input") from exc
    if not 12 <= len(password) <= 128 or size > 512:
        raise AuthError("invalid_input")


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        return (
            PASSWORD_HASHER.verify(encoded or DUMMY_HASH, password)
            and encoded is not None
        )
    except (VerificationError, InvalidHashError):
        return False


def random_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    # 토큰 자체가 256비트 난수이므로 비밀번호와 달리 SHA-256 검증 해시가 적합하다.
    try:
        return hashlib.sha256(token.encode()).hexdigest()
    except UnicodeEncodeError as exc:
        raise AuthError("invalid_input") from exc


def safe_redirect(value: str) -> str:
    # 인코딩/백슬래시/제어문자로 브라우저의 URL 해석이 달라지는 경로도 보수적으로 거절한다.
    if (
        not value.startswith("/")
        or value.startswith("//")
        or any(c in value for c in ("\\", "%", "#"))
        or any(ord(c) <= 32 or ord(c) == 127 for c in value)
        or len(value) > 1024
    ):
        raise AuthError("invalid_redirect")
    return value


class TokenCodec:
    def __init__(self, settings):
        self.settings = settings
        self.key = base64.b64decode(settings.jwt_key)

    def encode_token(
        self, *, kind: str, subject: str, session_id: str, expires_at: datetime
    ) -> str:
        now = int(datetime.now(UTC).timestamp())
        return jwt.encode(
            {
                "iss": self.settings.issuer,
                "aud": self.settings.audience,
                "sub": subject,
                "sid": session_id,
                "jti": random_token(),
                "iat": now,
                "nbf": now,
                "exp": int(expires_at.timestamp()),
                "type": kind,
            },
            self.key,
            algorithm="HS256",
            headers={"typ": "JWT"},
        )

    def decode_token(self, token: str, kind: str) -> dict:
        try:
            if len(token) > 4096:
                raise ValueError
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["HS256"],
                issuer=self.settings.issuer,
                audience=self.settings.audience,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "sid",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                        "type",
                    ],
                    "strict_aud": True,
                },
            )
            if (
                claims["type"] != kind
                or not isinstance(claims["jti"], str)
                or not claims["jti"]
            ):
                raise ValueError
            if (
                any(type(claims[k]) is not int for k in ("iat", "nbf", "exp"))
                or claims["exp"] <= claims["iat"]
            ):
                raise ValueError
            UUID(claims["sub"])
            UUID(claims["sid"])
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError) as exc:
            raise AuthError("invalid_token") from exc

    def rate_key(self, scope: str, subject: str, bucket: int) -> str:
        return hmac.new(
            self.key, f"rate:{scope}:{subject}:{bucket}".encode(), hashlib.sha256
        ).hexdigest()
