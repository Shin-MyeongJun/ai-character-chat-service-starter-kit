"""외부 메일·Google 통신 경계. 민감한 요청/응답을 로깅하지 않고 오류를 일반화한다."""

import asyncio
import hmac
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

import httpx
import jwt

from app.modules.identity import types as Types


class MailSender(Protocol):
    async def send_mail(self, recipient: str, purpose: str, link: str) -> None: ...


class GoogleVerifier(Protocol):
    async def verify_code(
        self, code: str, verifier: str, nonce: str
    ) -> Types.GoogleIdentityInfo: ...


class SMTPMailSender:
    def __init__(self, settings):
        self.settings = settings

    async def send_mail(self, recipient: str, purpose: str, link: str) -> None:
        def deliver():
            settings = self.settings
            message = EmailMessage()
            message["From"] = settings.smtp_from
            message["To"] = recipient
            message["Subject"] = (
                "이메일 인증" if purpose == "verify" else "비밀번호 재설정"
            )
            message.set_content(
                f"요청한 작업을 계속하려면 아래 링크를 여세요. 요청하지 않았다면 무시하세요.\n\n{link}\n"
            )
            smtp_type = smtplib.SMTP_SSL if settings.smtp_tls == "ssl" else smtplib.SMTP
            kwargs = (
                {"context": ssl.create_default_context()}
                if settings.smtp_tls == "ssl"
                else {}
            )
            with smtp_type(
                settings.smtp_host, settings.smtp_port, timeout=10, **kwargs
            ) as smtp:
                if settings.smtp_tls == "starttls":
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)

        try:
            await asyncio.to_thread(deliver)
        except (OSError, smtplib.SMTPException) as exc:
            # 메일 장애를 개발 로그 발송이나 성공 응답으로 바꾸지 않는다.
            raise Types.AuthError("mail_unavailable") from exc


class GoogleOIDCVerifier:
    def __init__(self, settings):
        self.settings = settings
        # 키 주소와 알고리즘은 고정한다. 토큰의 jku/x5u를 신뢰하지 않는다.
        self.keys = jwt.PyJWKClient(
            "https://www.googleapis.com/oauth2/v3/certs", timeout=10, lifespan=300
        )

    def verify_id_token(self, token: str, nonce: str) -> Types.GoogleIdentityInfo:
        try:
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.google_client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
                options={
                    "require": [
                        "iss",
                        "aud",
                        "exp",
                        "iat",
                        "sub",
                        "email",
                        "email_verified",
                        "nonce",
                    ]
                },
            )
            if (
                claims.get("azp", self.settings.google_client_id)
                != self.settings.google_client_id
            ):
                raise ValueError
            if (
                isinstance(claims["aud"], list)
                and len(claims["aud"]) > 1
                and "azp" not in claims
            ):
                raise ValueError
            if (
                claims["email_verified"] is not True
                or not isinstance(claims["nonce"], str)
                or not hmac.compare_digest(claims["nonce"], nonce)
            ):
                raise ValueError
            if (
                not isinstance(claims["sub"], str)
                or not 1 <= len(claims["sub"]) <= 255
                or not isinstance(claims["email"], str)
            ):
                raise ValueError
            return Types.GoogleIdentityInfo(claims["sub"], claims["email"])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise Types.AuthError("invalid_google_login") from exc

    async def verify_code(
        self, code: str, verifier: str, nonce: str
    ) -> Types.GoogleIdentityInfo:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "code_verifier": verifier,
                        "client_id": self.settings.google_client_id,
                        "client_secret": self.settings.google_client_secret,
                        "redirect_uri": self.settings.google_callback_url,
                    },
                )
                response.raise_for_status()
                token = response.json()["id_token"]
            return await asyncio.to_thread(self.verify_id_token, token, nonce)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise Types.AuthError("invalid_google_login") from exc
