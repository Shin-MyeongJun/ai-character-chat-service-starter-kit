"""Durable mail claims and bounded retries; never holds a DB session during SMTP."""

import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.fernet import InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.db.types import SessionFactory
from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper
from app.modules.identity.settings import AuthSettings

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


def _current_time() -> datetime:
    return datetime.now(UTC)


class MailDeliveryService:
    def __init__(
        self,
        session_factory: SessionFactory,
        settings: AuthSettings,
        *,
        clock: Callable[[], datetime] = _current_time,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.clock = clock

    async def _prepare_mail(
        self, session: AsyncSession, info: Types.MailOutboxInfo, now: datetime
    ) -> tuple[Types.ActionMailInfo | None, str | None]:
        action = PersistenceMapper.action_entity_to_info(
            await Repository.get_action_token(session, info.token_hash)
        )
        if action is None or action.consumed_at is not None or action.expires_at <= now:
            return None, "token_inactive"
        # Read only: never acquire user/token locks after the outbox lock. Request
        # writes use user -> token; cleanup can cascade token -> outbox.
        user = PersistenceMapper.user_entity_to_credential_info(
            await Repository.get_user(session, action.user_id, refresh=True)
        )
        if user is None or user.status != "active" or user.password_hash is None:
            return None, "account_ineligible"
        eligible = (action.purpose == "reset" and user.user.email_verified) or (
            action.purpose == "verify"
            and not user.user.email_verified
            and user.pending_expires_at is not None
            and user.pending_expires_at > now
        )
        if not eligible:
            return None, "account_ineligible"
        if info.encrypted_token is None:
            return None, "payload_invalid"
        try:
            token = Security.decrypt_mail_token(
                info.encrypted_token, info.token_hash, self.settings
            )
        except (InvalidToken, UnicodeError):
            return None, "payload_invalid"
        return Types.ActionMailInfo(user.user.email, action.purpose, token), None

    async def claim_mail(self) -> Types.MailDeliveryInfo | None:
        claim_token = uuid4()
        async with self.session_factory() as session, use_case_transaction(session):
            info = PersistenceMapper.mail_outbox_entity_to_info(
                await Repository.get_due_mail_outbox(session, self.clock())
            )
            if info is None:
                return None
            now = self.clock()
            mail, reason = await self._prepare_mail(session, info, now)
            if info.attempt_count >= MAX_ATTEMPTS:
                mail, reason = None, "attempts_exhausted"
            status = (
                "processing"
                if mail is not None
                else (
                    "failed"
                    if reason in {"payload_invalid", "attempts_exhausted"}
                    else "cancelled"
                )
            )
            attempt_count = info.attempt_count + int(mail is not None)
            await Repository.update_mail_outbox(
                session,
                outbox_id=info.id,
                status=status,
                attempt_count=attempt_count,
                available_at=info.available_at,
                claim_token=claim_token if mail is not None else None,
                lease_until=now + timedelta(seconds=LEASE_SECONDS)
                if mail is not None
                else None,
                last_error=reason,
                clear_payload=mail is None,
            )
        logger.info(
            "auth_mail id=%s status=%s attempt=%s reason=%s",
            info.id,
            status,
            attempt_count,
            reason,
        )
        return Types.MailDeliveryInfo(info.id, claim_token, attempt_count, mail)

    async def complete_mail(self, command: Types.CompleteMailDeliveryCommand) -> bool:
        async with self.session_factory() as session, use_case_transaction(session):
            info = PersistenceMapper.mail_outbox_entity_to_info(
                await Repository.get_claimed_mail_outbox(
                    session, command.id, command.claim_token, self.clock()
                )
            )
            now = self.clock()
            if info is None or info.lease_until is None or info.lease_until <= now:
                logger.warning("auth_mail id=%s status=claim_lost", command.id)
                return False
            status: str = command.outcome
            reason: str | None = None
            available_at = now
            if command.outcome != "sent":
                reason = (
                    "smtp_transient" if command.outcome == "retry" else "smtp_permanent"
                )
                status = "failed"
                if command.outcome == "retry" and info.attempt_count < MAX_ATTEMPTS:
                    # 30, 60, 120, 240 seconds plus up to 25% jitter. Retry the
                    # same proof; issuing a new token here would invalidate mail.
                    delay_seconds = 30 * 2 ** (info.attempt_count - 1)
                    available_at = now + timedelta(
                        seconds=delay_seconds
                        + secrets.randbelow(delay_seconds // 4 + 1)
                    )
                    action = PersistenceMapper.action_entity_to_info(
                        await Repository.get_action_token(session, info.token_hash)
                    )
                    if (
                        action is not None
                        and action.consumed_at is None
                        and action.expires_at > available_at
                    ):
                        status = "pending"
                    else:
                        status, reason = "cancelled", "token_inactive"
                elif command.outcome == "retry":
                    reason = "attempts_exhausted"
            await Repository.update_mail_outbox(
                session,
                outbox_id=info.id,
                status=status,
                attempt_count=info.attempt_count,
                available_at=available_at,
                claim_token=None,
                lease_until=None,
                last_error=reason,
                clear_payload=status != "pending",
            )
        logger.info(
            "auth_mail id=%s status=%s attempt=%s reason=%s",
            info.id,
            status,
            info.attempt_count,
            reason,
        )
        return True
