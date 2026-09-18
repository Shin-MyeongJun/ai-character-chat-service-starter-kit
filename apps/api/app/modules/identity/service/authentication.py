"""인증 유스케이스와 트랜잭션 경계. 사용자 → 세션/토큰 순으로 잠가 폐기를 직렬화한다."""

import asyncio
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.db.transaction import use_case_transaction
from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


class AuthenticationService:
    def __init__(self, sessions, settings, mailer):
        self.sessions = sessions
        self.settings = settings
        self.mailer = mailer
        self.codec = Security.TokenCodec(settings)

    async def check_rate_limit(self, command: Types.RateLimitCommand) -> None:
        now = datetime.now(UTC)
        bucket = int(now.timestamp()) // command.seconds
        key = self.codec.rate_key(command.scope, command.subject, bucket)
        async with self.sessions() as session, use_case_transaction(session):
            allowed = PersistenceMapper.scalar_row_to_used(
                await Repository.increment_rate_limit(
                    session,
                    key,
                    command.limit,
                    datetime.fromtimestamp((bucket + 1) * command.seconds, UTC),
                )
            )
        if not allowed:
            raise Types.AuthError("rate_limited")

    async def _check_email_rate(self, scope, email, limit=5, seconds=900):
        await self.check_rate_limit(
            Types.RateLimitCommand(scope, email, limit, seconds)
        )

    async def _create_mail_token(self, session, user_id, purpose, now):
        token = Security.random_token()
        await Repository.invalidate_action_tokens(session, user_id, purpose, now)
        await Repository.create_action_token(
            session,
            user_id=user_id,
            token_hash=Security.token_hash(token),
            purpose=purpose,
            expires_at=now + timedelta(minutes=30 if purpose == "verify" else 15),
        )
        return token

    async def _send_action_mail(self, email, purpose, token):
        page = "/verify-email" if purpose == "verify" else "/reset-password"
        # fragment는 웹서버 요청 로그와 Referer에 토큰이 실리지 않도록 한다.
        await self.mailer.send_mail(
            email, purpose, self.settings.public_origin + page + "#token=" + token
        )

    async def register_user(self, command: Types.CredentialsCommand) -> None:
        email = Security.normalize_email(command.email)
        Security.validate_password(command.password)
        await self._check_email_rate("register", email)
        await self._check_email_rate("mail:verify", email)
        encoded = await asyncio.to_thread(
            Security.PASSWORD_HASHER.hash, command.password
        )
        now, token = datetime.now(UTC), None
        async with self.sessions() as session, use_case_transaction(session):
            await Repository.lock_identity(session, "email:" + email)
            user = PersistenceMapper.user_entity_to_credential_info(
                await Repository.get_user_by_email(session, email)
            )
            if (
                user is not None
                and user.pending_expires_at is not None
                and user.pending_expires_at <= now
                and not user.user.email_verified
            ):
                await Repository.delete_pending_user(session, user.user.id)
                user = None
            if user is None:
                user = PersistenceMapper.user_entity_to_credential_info(
                    await Repository.create_user(
                        session,
                        user_id=uuid4(),
                        email=email,
                        password_hash=encoded,
                        verified=False,
                        pending_expires_at=now + timedelta(days=7),
                    )
                )
                if user is not None:
                    token = await self._create_mail_token(
                        session, user.user.id, "verify", now
                    )
            # 중복 가입은 기존 비밀번호를 덮어쓰거나 이메일 인증 상태를 알려주지 않는다.
        if token is not None:
            await self._send_action_mail(email, "verify", token)

    async def resend_verification(self, command: Types.EmailCommand) -> None:
        await self._request_action_mail(command, "verify")

    async def request_password_reset(self, command: Types.EmailCommand) -> None:
        await self._request_action_mail(command, "reset")

    async def _request_action_mail(self, command, purpose):
        email = Security.normalize_email(command.email)
        # 가입/재발송은 별도 IP 제한 외에 동일 메일 발송 버킷도 공유한다.
        await self._check_email_rate("mail:" + purpose, email)
        now, token = datetime.now(UTC), None
        async with self.sessions() as session, use_case_transaction(session):
            user = PersistenceMapper.user_entity_to_credential_info(
                await Repository.get_user_by_email(session, email)
            )
            if (
                user is not None
                and user.status == "active"
                and user.password_hash is not None
            ):
                eligible = (purpose == "reset" and user.user.email_verified) or (
                    purpose == "verify"
                    and not user.user.email_verified
                    and user.pending_expires_at is not None
                    and user.pending_expires_at > now
                )
                if eligible:
                    token = await self._create_mail_token(
                        session, user.user.id, purpose, now
                    )
        if token is not None:
            await self._send_action_mail(email, purpose, token)

    async def _consume_action(self, session, token, purpose, now):
        info = PersistenceMapper.action_entity_to_info(
            await Repository.get_action_token(session, Security.token_hash(token))
        )
        if (
            info is None
            or info.purpose != purpose
            or info.consumed_at is not None
            or info.expires_at <= now
        ):
            raise Types.AuthError("invalid_action_token")
        user = PersistenceMapper.user_entity_to_credential_info(
            await Repository.get_locked_user(session, info.user_id)
        )
        if user is None or user.status != "active" or user.password_hash is None:
            raise Types.AuthError("invalid_action_token")
        if purpose == "verify" and (
            user.user.email_verified
            or user.pending_expires_at is None
            or user.pending_expires_at <= now
        ):
            raise Types.AuthError("invalid_action_token")
        if purpose == "reset" and not user.user.email_verified:
            raise Types.AuthError("invalid_action_token")
        used = PersistenceMapper.scalar_row_to_used(
            await Repository.consume_action_token(session, info.id, now)
        )
        if not used:
            raise Types.AuthError("invalid_action_token")
        return user

    async def verify_email(self, command: Types.TokenCommand) -> Types.UserInfo:
        now = datetime.now(UTC)
        async with self.sessions() as session, use_case_transaction(session):
            user = await self._consume_action(session, command.token, "verify", now)
            verified = PersistenceMapper.user_entity_to_credential_info(
                await Repository.verify_user_email(session, user.user.id)
            )
            return verified.user

    async def reset_password(self, command: Types.ResetPasswordCommand) -> None:
        Security.validate_password(command.password)
        encoded = await asyncio.to_thread(
            Security.PASSWORD_HASHER.hash, command.password
        )
        now = datetime.now(UTC)
        async with self.sessions() as session, use_case_transaction(session):
            user = await self._consume_action(session, command.token, "reset", now)
            await Repository.update_password(session, user.user.id, encoded)
            await Repository.invalidate_action_tokens(session, user.user.id, None, now)
            await Repository.revoke_user_sessions(session, user.user.id, now)

    async def _issue_session(self, session, user, now):
        session_id = uuid4()
        expires_at = now + timedelta(seconds=self.settings.session_seconds)
        login = self._encode_login(user.user, session_id, now, expires_at)
        await Repository.create_session(
            session,
            session_id=session_id,
            user_id=user.user.id,
            refresh_hash=Security.token_hash(login.refresh_token),
            now=now,
            expires_at=expires_at,
        )
        return login

    def _encode_login(self, user, session_id, now, expires_at):
        access = self.codec.encode_token(
            kind="access",
            subject=str(user.id),
            session_id=str(session_id),
            expires_at=min(
                expires_at, now + timedelta(seconds=self.settings.access_seconds)
            ),
        )
        refresh = self.codec.encode_token(
            kind="refresh",
            subject=str(user.id),
            session_id=str(session_id),
            expires_at=expires_at,
        )
        return Types.LoginInfo(user, access, refresh, expires_at)

    async def login_user(self, command: Types.CredentialsCommand) -> Types.LoginInfo:
        email = Security.normalize_email(command.email)
        Security.validate_password(command.password)
        await self._check_email_rate("login", email, limit=10, seconds=300)
        async with self.sessions() as session, use_case_transaction(session):
            user = PersistenceMapper.user_entity_to_credential_info(
                await Repository.get_user_by_email(session, email)
            )
            valid = await asyncio.to_thread(
                Security.verify_password,
                command.password,
                user.password_hash if user else None,
            )
            if (
                not valid
                or user is None
                or user.status != "active"
                or not user.user.email_verified
            ):
                raise Types.AuthError("invalid_credentials")
            if Security.PASSWORD_HASHER.check_needs_rehash(user.password_hash):
                await Repository.update_password(
                    session,
                    user.user.id,
                    await asyncio.to_thread(
                        Security.PASSWORD_HASHER.hash, command.password
                    ),
                )
            return await self._issue_session(session, user, datetime.now(UTC))

    async def _require_session(self, session, claims, now):
        user = PersistenceMapper.user_entity_to_credential_info(
            await Repository.get_locked_user(session, UUID(claims["sub"]))
        )
        info = PersistenceMapper.session_entity_to_info(
            await Repository.get_session(session, UUID(claims["sid"]))
        )
        now = datetime.now(UTC)  # 잠금 대기 중 만료한 세션도 거절한다.
        if (
            user is None
            or user.status != "active"
            or not user.user.email_verified
            or info is None
            or info.user_id != user.user.id
            or info.revoked_at is not None
            or info.expires_at <= now
        ):
            raise Types.AuthError("invalid_session")
        return user, info

    async def get_authenticated_user(
        self, command: Types.TokenCommand
    ) -> Types.UserInfo:
        claims = self.codec.decode_token(command.token, "access")
        async with self.sessions() as session, use_case_transaction(session):
            user, _ = await self._require_session(session, claims, datetime.now(UTC))
            return user.user

    async def refresh_session(self, command: Types.TokenCommand) -> Types.LoginInfo:
        claims = self.codec.decode_token(command.token, "refresh")
        now, reused, login = datetime.now(UTC), False, None
        async with self.sessions() as session, use_case_transaction(session):
            user, info = await self._require_session(session, claims, now)
            if not hmac.compare_digest(
                info.refresh_hash, Security.token_hash(command.token)
            ):
                await Repository.revoke_session(session, info.id, now)
                reused = True
            else:
                login = self._encode_login(user.user, info.id, now, info.expires_at)
                await Repository.rotate_session(
                    session, info.id, Security.token_hash(login.refresh_token)
                )
        # 폐기 트랜잭션을 커밋한 뒤 실패를 내보내야 재사용 공격에서도 폐기가 유지된다.
        if reused:
            raise Types.AuthError("refresh_reused")
        return login

    async def logout_session(self, command: Types.LogoutCommand) -> None:
        try:
            claims = self.codec.decode_token(command.refresh_token, "refresh")
        except Types.AuthError:
            try:
                claims = self.codec.decode_token(command.access_token, "access")
            except Types.AuthError:
                # 만료·훼손 토큰으로 다른 세션을 폐기하지 않는다. HTTP는 쿠키를 항상 삭제한다.
                return
        async with self.sessions() as session, use_case_transaction(session):
            user = PersistenceMapper.user_entity_to_credential_info(
                await Repository.get_locked_user(session, UUID(claims["sub"]))
            )
            info = PersistenceMapper.session_entity_to_info(
                await Repository.get_session(session, UUID(claims["sid"]))
            )
            if user is not None and info is not None and info.user_id == user.user.id:
                await Repository.revoke_session(session, info.id, datetime.now(UTC))

    async def logout_all_sessions(self, command: Types.TokenCommand) -> None:
        claims = self.codec.decode_token(command.token, "access")
        now = datetime.now(UTC)
        async with self.sessions() as session, use_case_transaction(session):
            user, _ = await self._require_session(session, claims, now)
            await Repository.revoke_user_sessions(session, user.user.id, now)

    async def cleanup_expired_auth(self) -> Types.CleanupInfo:
        async with self.sessions() as session, use_case_transaction(session):
            return PersistenceMapper.cleanup_row_to_info(
                await Repository.delete_expired_records(session, datetime.now(UTC))
            )
