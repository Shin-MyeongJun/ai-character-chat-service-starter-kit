"""OAuth state consumption and provider/sub account linking."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.transaction import use_case_transaction
from app.modules.identity import repository as Repository
from app.modules.identity import security as Security
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


async def create_google_state(
    session: AsyncSession, command: Types.GoogleStateCommand
) -> None:
    async with use_case_transaction(session):
        await Repository.create_oauth_attempt(
            session,
            Security.token_hash(command.state),
            datetime.now(UTC) + timedelta(minutes=10),
        )


async def consume_google_state(
    session: AsyncSession, command: Types.GoogleStateCommand
) -> None:
    async with use_case_transaction(session):
        used = PersistenceMapper.scalar_row_to_used(
            await Repository.consume_oauth_attempt(
                session, Security.token_hash(command.state), datetime.now(UTC)
            )
        )
        if not used:
            raise Types.AuthError("invalid_google_login")


async def link_google_account(
    session: AsyncSession, command: Types.LinkGoogleAccountCommand
) -> Types.CredentialInfo:
    email = Security.normalize_email(command.email)
    async with use_case_transaction(session):
        await Repository.lock_identity(session, "google:" + command.sub)
        await Repository.lock_identity(session, "email:" + email)
        user = PersistenceMapper.user_entity_to_credential_info(
            await Repository.get_google_user(session, command.sub)
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
            await Repository.create_google_account(session, user.user.id, command.sub)
        # 공급자 이메일이 바뀌어도 sub가 계정의 기준이다. 이메일을 자동 변경/병합하지 않는다.
        if user.status != "active" or not user.user.email_verified:
            raise Types.AuthError("invalid_google_login")
        return user
