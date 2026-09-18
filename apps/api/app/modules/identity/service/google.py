"""OIDC 시작/콜백 유스케이스. 외부 증명 검증 후 provider+sub로 계정을 식별한다."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from app.db.transaction import use_case_transaction
from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


class GoogleLoginService:
    def __init__(self, authentication, verifier):
        self.auth = authentication
        self.settings = authentication.settings
        self.verifier = verifier
        self.fernet = Fernet(self.settings.flow_key.encode())

    async def start_google_login(
        self, command: Types.GoogleStartCommand
    ) -> Types.GoogleStartInfo:
        redirect = Security.safe_redirect(command.redirect)
        if not self.settings.google_client_id:
            raise Types.AuthError("google_not_configured")
        state, nonce, verifier = (Security.random_token() for _ in range(3))
        now = datetime.now(UTC)
        async with self.auth.sessions() as session, use_case_transaction(session):
            await Repository.create_oauth_attempt(
                session, Security.token_hash(state), now + timedelta(minutes=10)
            )
        # PKCE 원문은 DB 대신 암호화·인증된 HttpOnly 쿠키에만 담는다.
        cookie = self.fernet.encrypt(
            json.dumps(
                {
                    "state": state,
                    "nonce": nonce,
                    "verifier": verifier,
                    "redirect": redirect,
                }
            ).encode()
        ).decode()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": self.settings.google_client_id,
                "redirect_uri": self.settings.google_callback_url,
                "response_type": "code",
                "scope": "openid email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return Types.GoogleStartInfo(url, cookie)

    async def complete_google_login(
        self, command: Types.GoogleCallbackCommand
    ) -> Types.GoogleLoginInfo:
        try:
            flow = json.loads(self.fernet.decrypt(command.cookie.encode(), ttl=600))
            if not hmac.compare_digest(flow["state"], command.state):
                raise ValueError
            redirect = Security.safe_redirect(flow["redirect"])
        except (InvalidToken, ValueError, KeyError, TypeError) as exc:
            raise Types.AuthError("invalid_google_login") from exc
        async with self.auth.sessions() as session, use_case_transaction(session):
            used = PersistenceMapper.scalar_row_to_used(
                await Repository.consume_oauth_attempt(
                    session, Security.token_hash(command.state), datetime.now(UTC)
                )
            )
            if not used:
                raise Types.AuthError("invalid_google_login")
        # 상태 소모 후 네트워크를 호출한다. 콜백 중복/응답 유실은 새 로그인 시작으로 복구한다.
        identity = await self.verifier.verify_code(
            command.code, flow["verifier"], flow["nonce"]
        )
        email = Security.normalize_email(identity.email)
        async with self.auth.sessions() as session, use_case_transaction(session):
            await Repository.lock_identity(session, "google:" + identity.sub)
            await Repository.lock_identity(session, "email:" + email)
            user = PersistenceMapper.user_entity_to_credential_info(
                await Repository.get_google_user(session, identity.sub)
            )
            if user is None:
                conflict = PersistenceMapper.user_entity_to_credential_info(
                    await Repository.get_user_by_email(session, email)
                )
                if conflict is not None:
                    raise Types.AuthError("account_conflict")
                user = PersistenceMapper.user_entity_to_credential_info(
                    await Repository.create_user(
                        session,
                        user_id=uuid4(),
                        email=email,
                        password_hash=None,
                        verified=True,
                        pending_expires_at=None,
                    )
                )
                if user is None:
                    raise Types.AuthError("account_conflict")
                await Repository.create_google_account(
                    session, user.user.id, identity.sub
                )
            # 공급자 이메일이 바뀌어도 sub가 계정의 기준이다. 이메일을 자동 변경/병합하지 않는다.
            if user.status != "active" or not user.user.email_verified:
                raise Types.AuthError("invalid_google_login")
            return Types.GoogleLoginInfo(
                await self.auth._issue_session(session, user, datetime.now(UTC)),
                redirect,
            )
