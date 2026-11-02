"""HTTP only commits intent. The separate worker claims, sends, then acknowledges."""

from app.modules.identity import types as Types
from app.modules.identity.adapters import MailSender
from app.modules.identity.service.authentication import AuthenticationService
from app.modules.identity.service.mail_delivery import MailDeliveryService


class AuthenticationMailWorkflow:
    def __init__(
        self, authentication: AuthenticationService, mailer: MailSender
    ) -> None:
        self.auth = authentication
        self.mailer = mailer
        self.delivery = MailDeliveryService(
            authentication.sessions, authentication.settings
        )

    async def deliver_next_mail(self) -> bool:
        info = await self.delivery.claim_mail()
        if info is None:
            return False
        if info.mail is None:
            return True
        mail = info.mail
        page = "/verify-email" if mail.purpose == "verify" else "/reset-password"
        outcome = Types.CompleteMailDeliveryCommand(info.id, info.claim_token, "sent")
        try:
            await self.mailer.send_mail(
                mail.email,
                mail.purpose,
                self.auth.settings.public_origin + page + "#token=" + mail.token,
            )
        except Types.AuthError as exc:
            if exc.code != "mail_unavailable":
                raise
            can_retry = not isinstance(exc, Types.MailDeliveryError) or exc.can_retry
            outcome = Types.CompleteMailDeliveryCommand(
                info.id, info.claim_token, "retry" if can_retry else "failed"
            )
        # Unexpected errors/cancellation leave the durable lease for recovery.
        # SMTP acceptance and this commit cannot be made atomic (at-least-once).
        await self.delivery.complete_mail(outcome)
        return True

    async def register_user(self, command: Types.CredentialsCommand) -> None:
        await self.auth.register_pending_user(command)

    async def resend_verification(self, command: Types.EmailCommand) -> None:
        await self.auth.prepare_action_mail(
            Types.PrepareActionMailCommand(command.email, "verify")
        )

    async def request_password_reset(self, command: Types.EmailCommand) -> None:
        await self.auth.prepare_action_mail(
            Types.PrepareActionMailCommand(command.email, "reset")
        )
