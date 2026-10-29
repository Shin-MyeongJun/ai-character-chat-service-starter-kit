"""인증 공개 요청·결과 값. HTTP/ORM과 분리하며 민감 값은 repr에서 숨긴다."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict
from uuid import UUID


class AuthTokenClaims(TypedDict):
    """Existing validated JWT claims; decoding retains the original extension keys."""

    iss: str
    aud: str
    sub: str
    sid: str
    jti: str
    iat: int
    nbf: int
    exp: int
    type: str


@dataclass(frozen=True, slots=True)
class GetUserCommand:
    user_id: UUID


@dataclass(frozen=True, slots=True)
class UserAccessInfo:
    id: UUID
    role: str
    status: str


class AuthError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CredentialsCommand:
    email: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class EmailCommand:
    email: str


@dataclass(frozen=True)
class TokenCommand:
    token: str = field(repr=False)


@dataclass(frozen=True)
class LogoutCommand:
    refresh_token: str = field(repr=False)
    access_token: str = field(repr=False)


@dataclass(frozen=True)
class ResetPasswordCommand:
    token: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class RateLimitCommand:
    scope: str
    subject: str = field(repr=False)
    limit: int
    seconds: int


@dataclass(frozen=True)
class GoogleStartCommand:
    redirect: str = "/"


@dataclass(frozen=True)
class GoogleCallbackCommand:
    state: str = field(repr=False)
    code: str = field(repr=False)
    cookie: str = field(repr=False)


@dataclass(frozen=True)
class GoogleIdentityInfo:
    sub: str
    email: str


@dataclass(frozen=True)
class UserInfo:
    id: UUID
    email: str
    email_verified: bool


@dataclass(frozen=True)
class CredentialInfo:
    user: UserInfo
    password_hash: str | None = field(repr=False)
    status: str
    pending_expires_at: datetime | None


@dataclass(frozen=True)
class SessionInfo:
    id: UUID
    user_id: UUID
    refresh_hash: str = field(repr=False)
    expires_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True)
class ActionTokenInfo:
    id: UUID
    user_id: UUID
    purpose: str
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True)
class LoginInfo:
    user: UserInfo
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class GoogleStartInfo:
    url: str = field(repr=False)
    cookie: str = field(repr=False)


@dataclass(frozen=True)
class GoogleLoginInfo:
    login: LoginInfo
    redirect: str


@dataclass(frozen=True)
class CleanupInfo:
    users: int
    tokens: int
    sessions: int
    attempts: int
    rate_limits: int


@dataclass(frozen=True, slots=True)
class ActionMailInfo:
    email: str
    purpose: str
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PrepareActionMailCommand:
    email: str
    purpose: str


@dataclass(frozen=True, slots=True)
class IssueSessionCommand:
    user: CredentialInfo
    now: datetime


@dataclass(frozen=True, slots=True)
class GoogleStateCommand:
    state: str


@dataclass(frozen=True, slots=True)
class LinkGoogleAccountCommand:
    sub: str
    email: str
