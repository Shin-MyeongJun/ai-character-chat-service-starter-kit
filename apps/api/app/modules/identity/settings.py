"""인증 설정을 시작 시 검증한다. 운영에서 개발 키나 메일 대체 처리를 허용하지 않는다."""

import base64
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from cryptography.fernet import Fernet


@dataclass(frozen=True)
class AuthSettings:
    jwt_key: str = field(repr=False)
    flow_key: str = field(repr=False)
    issuer: str = "chatkit"
    audience: str = "chatkit-api"
    public_origin: str = "http://localhost:8000"
    allowed_origins: tuple[str, ...] = ("http://localhost:8000",)
    secure_cookies: bool = True
    environment: str = "production"
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    google_callback_url: str = "http://localhost:8000/auth/google/callback"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = field(default="", repr=False)
    smtp_from: str = "noreply@example.com"
    smtp_tls: str = "none"
    access_seconds: int = 900
    session_seconds: int = 14 * 86400

    def __post_init__(self):
        # HS256 키는 base64로 인코딩한 32바이트 이상 난수만 설정한다.
        try:
            if len(base64.b64decode(self.jwt_key, validate=True)) < 32:
                raise ValueError
            Fernet(self.flow_key.encode())
        except (ValueError, TypeError) as exc:
            raise ValueError(
                "AUTH_JWT_KEY / AUTH_FLOW_KEY must be valid random keys"
            ) from exc
        if not self.issuer or not self.audience:
            raise ValueError("AUTH_ISSUER and AUTH_AUDIENCE are required")
        for origin in (self.public_origin, *self.allowed_origins):
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.netloc
                or url.path
                or url.query
                or url.fragment
                or url.username
                or url.password
            ):
                raise ValueError("Authentication origins must be exact HTTP(S) origins")
        if self.public_origin not in self.allowed_origins:
            raise ValueError("AUTH_PUBLIC_ORIGIN must be allowed")
        if self.google_callback_url != self.public_origin + "/auth/google/callback":
            raise ValueError("Google callback must match the fixed public origin route")
        if (
            self.smtp_tls not in {"none", "starttls", "ssl"}
            or not self.smtp_host
            or not self.smtp_from
        ):
            raise ValueError("Explicit SMTP configuration is required")
        if bool(self.google_client_id) != bool(self.google_client_secret):
            raise ValueError("Both Google credentials must be configured")
        if self.environment not in {"local", "test"}:
            if not self.secure_cookies or any(
                not x.startswith("https://") for x in self.allowed_origins
            ):
                raise ValueError("Production requires HTTPS and Secure cookies")
            if self.smtp_tls == "none" or not self.smtp_user or not self.smtp_password:
                raise ValueError("Production requires authenticated TLS SMTP")
        if self.access_seconds != 900 or self.session_seconds != 14 * 86400:
            raise ValueError("Session lifetime policy is 15 minutes / 14 days")

    def cookie_name(self, kind: str) -> str:
        return ("__Host-" if self.secure_cookies else "") + "chatkit_" + kind


def load_auth_settings() -> AuthSettings:
    origin = os.getenv("AUTH_PUBLIC_ORIGIN", "http://localhost:8000").rstrip("/")
    return AuthSettings(
        jwt_key=os.environ["AUTH_JWT_KEY"],
        flow_key=os.environ["AUTH_FLOW_KEY"],
        issuer=os.getenv("AUTH_ISSUER", "chatkit"),
        audience=os.getenv("AUTH_AUDIENCE", "chatkit-api"),
        public_origin=origin,
        allowed_origins=tuple(
            dict.fromkeys(
                [
                    origin,
                    *filter(
                        None,
                        (x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",")),
                    ),
                ]
            )
        ),
        environment=os.getenv("ENVIRONMENT", "production"),
        secure_cookies=os.getenv("AUTH_SECURE_COOKIES", "true").lower() == "true",
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        google_callback_url=os.getenv(
            "GOOGLE_CALLBACK_URL", origin + "/auth/google/callback"
        ),
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.environ["SMTP_FROM"],
        smtp_tls=os.getenv("SMTP_TLS", "starttls"),
    )
