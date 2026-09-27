"""Commit account/token state before sending mail; SMTP failure preserves it."""

from app.modules.identity import types as Types
from app.modules.identity.service.authentication import AuthenticationService


class AuthenticationMailWorkflow:
    def __init__(self, authentication: AuthenticationService, mailer):
        self.auth = authentication
        self.mailer = mailer

    async def _send_action_mail(self, value):
        if value is None:
            return
        page = "/verify-email" if value.purpose == "verify" else "/reset-password"
        await self.mailer.send_mail(
            value.email,
            value.purpose,
            self.auth.settings.public_origin + page + "#token=" + value.token,
        )

    async def register_user(self, command: Types.CredentialsCommand) -> None:
        await self._send_action_mail(await self.auth.register_pending_user(command))

    async def resend_verification(self, command: Types.EmailCommand) -> None:
        await self._send_action_mail(
            await self.auth.prepare_action_mail(
                Types.PrepareActionMailCommand(command.email, "verify")
            )
        )

    async def request_password_reset(self, command: Types.EmailCommand) -> None:
        await self._send_action_mail(
            await self.auth.prepare_action_mail(
                Types.PrepareActionMailCommand(command.email, "reset")
            )
        )
