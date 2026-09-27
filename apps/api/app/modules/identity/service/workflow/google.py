"""OIDC 시작/콜백 유스케이스. 외부 증명 검증 후 provider+sub로 계정을 식별한다."""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken

from app.db.transaction import use_case_transaction
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.service import google as GoogleCommandService


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
        async with self.auth.sessions() as session:
            await GoogleCommandService.create_google_state(
                session, Types.GoogleStateCommand(state)
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
        async with self.auth.sessions() as session:
            await GoogleCommandService.consume_google_state(
                session, Types.GoogleStateCommand(command.state)
            )
        # 상태 소모 후 네트워크를 호출한다. 콜백 중복/응답 유실은 새 로그인 시작으로 복구한다.
        identity = await self.verifier.verify_code(
            command.code, flow["verifier"], flow["nonce"]
        )
        async with self.auth.sessions() as session, use_case_transaction(session):
            user = await GoogleCommandService.link_google_account(
                session, Types.LinkGoogleAccountCommand(identity.sub, identity.email)
            )
            login = await self.auth.issue_session(
                session, Types.IssueSessionCommand(user, datetime.now(UTC))
            )
            return Types.GoogleLoginInfo(login, redirect)
