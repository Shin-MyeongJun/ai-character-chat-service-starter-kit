# 인증 테이블 조회·쓰기와 PostgreSQL 잠금을 담당한다. 상태 판단과 commit은 서비스 소유다.
from datetime import datetime
from typing import TypeAlias, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.idempotency import lock_key
from app.db.models.identity import (
    AuthActionToken,
    AuthOAuthAttempt,
    AuthRateLimit,
    AuthSession,
    User,
    UserOAuthAccount,
)

CleanupRow: TypeAlias = tuple[int, int, int, int, int]


async def get_user(
    session: AsyncSession, user_id: UUID, *, refresh: bool = False
) -> User | None:
    """사용자를 조회하고 인가 재검증 시 세션 캐시를 최신 DB 값으로 갱신한다."""
    return await session.get(User, user_id, populate_existing=refresh)


async def lock_identity(session: AsyncSession, key: str) -> None:
    # 행 생성 전에도 동일 이메일/Google sub의 경합을 직렬화한다.
    await lock_key(session, "identity", key)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == email).with_for_update()
    return (await session.scalars(statement)).first()


async def get_locked_user(session: AsyncSession, user_id: UUID) -> User | None:
    statement = select(User).where(User.id == user_id).with_for_update()
    return (await session.scalars(statement)).first()


async def get_google_user(session: AsyncSession, sub: str) -> User | None:
    statement = (
        select(User)
        .join(UserOAuthAccount, User.id == UserOAuthAccount.user_id)
        .where(
            UserOAuthAccount.provider == "google",
            UserOAuthAccount.provider_user_id == sub,
        )
        .with_for_update(of=User)
    )
    return (await session.scalars(statement)).first()


async def create_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    email: str,
    password_hash: str | None,
    verified: bool,
    pending_expires_at: datetime | None,
) -> User | None:
    result = await session.execute(
        insert(User)
        .values(
            id=user_id,
            email=email,
            password_hash=password_hash,
            email_verified=verified,
            pending_expires_at=pending_expires_at,
        )
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User)
    )
    return result.scalar_one_or_none()


async def create_google_account(session: AsyncSession, user_id: UUID, sub: str) -> None:
    await session.execute(
        insert(UserOAuthAccount).values(
            user_id=user_id, provider="google", provider_user_id=sub
        )
    )


async def verify_user_email(session: AsyncSession, user_id: UUID) -> User:
    return (
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(email_verified=True, pending_expires_at=None)
            .returning(User)
        )
    ).scalar_one()


async def update_password(
    session: AsyncSession, user_id: UUID, password_hash: str
) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(password_hash=password_hash)
    )


async def delete_pending_user(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        delete(User).where(
            User.id == user_id,
            User.email_verified.is_(False),
            User.pending_expires_at.is_not(None),
        )
    )


async def create_session(
    session: AsyncSession,
    *,
    session_id: UUID,
    user_id: UUID,
    refresh_hash: str,
    now: datetime,
    expires_at: datetime,
) -> None:
    await session.execute(
        insert(AuthSession).values(
            id=session_id,
            user_id=user_id,
            refresh_hash=refresh_hash,
            created_at=now,
            expires_at=expires_at,
        )
    )


async def get_session(session: AsyncSession, session_id: UUID) -> AuthSession | None:
    statement = (
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    return (await session.scalars(statement)).first()


async def rotate_session(
    session: AsyncSession, session_id: UUID, refresh_hash: str
) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(refresh_hash=refresh_hash)
    )


async def revoke_session(
    session: AsyncSession, session_id: UUID, now: datetime
) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_user_sessions(
    session: AsyncSession, user_id: UUID, now: datetime
) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def invalidate_action_tokens(
    session: AsyncSession, user_id: UUID, purpose: str | None, now: datetime
) -> None:
    statement = update(AuthActionToken).where(
        AuthActionToken.user_id == user_id, AuthActionToken.consumed_at.is_(None)
    )
    if purpose is not None:
        statement = statement.where(AuthActionToken.purpose == purpose)
    await session.execute(statement.values(consumed_at=now))


async def create_action_token(
    session: AsyncSession,
    *,
    user_id: UUID,
    token_hash: str,
    purpose: str,
    expires_at: datetime,
) -> None:
    await session.execute(
        insert(AuthActionToken).values(
            user_id=user_id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
    )


async def get_action_token(
    session: AsyncSession, token_hash: str
) -> AuthActionToken | None:
    # 사용자 ID를 먼저 읽고 사용자 → 토큰 순서로 잠근다. 재설정/로그인 사이 교착을 피한다.
    statement = select(AuthActionToken).where(AuthActionToken.token_hash == token_hash)
    return (await session.scalars(statement)).first()


async def consume_action_token(
    session: AsyncSession, token_id: UUID, now: datetime
) -> UUID | None:
    return await session.scalar(
        update(AuthActionToken)
        .where(
            AuthActionToken.id == token_id,
            AuthActionToken.consumed_at.is_(None),
            AuthActionToken.expires_at > func.clock_timestamp(),
        )
        .values(consumed_at=now)
        .returning(AuthActionToken.id)
    )


async def create_oauth_attempt(
    session: AsyncSession, state_hash: str, expires_at: datetime
) -> None:
    await session.execute(
        insert(AuthOAuthAttempt).values(state_hash=state_hash, expires_at=expires_at)
    )


async def consume_oauth_attempt(
    session: AsyncSession, state_hash: str, now: datetime
) -> str | None:
    return await session.scalar(
        update(AuthOAuthAttempt)
        .where(
            AuthOAuthAttempt.state_hash == state_hash,
            AuthOAuthAttempt.consumed_at.is_(None),
            AuthOAuthAttempt.expires_at > func.clock_timestamp(),
        )
        .values(consumed_at=now)
        .returning(AuthOAuthAttempt.state_hash)
    )


async def increment_rate_limit(
    session: AsyncSession, key: str, limit: int, expires_at: datetime
) -> int | None:
    # DB UPSERT가 여러 API 프로세스 사이에서도 원자적으로 상한을 적용한다.
    return await session.scalar(
        insert(AuthRateLimit)
        .values(key=key, count=1, expires_at=expires_at)
        .on_conflict_do_update(
            index_elements=[AuthRateLimit.key],
            set_={"count": AuthRateLimit.count + 1},
            where=AuthRateLimit.count < limit,
        )
        .returning(AuthRateLimit.count)
    )


async def delete_expired_records(session: AsyncSession, now: datetime) -> CleanupRow:
    deletion_counts: list[int] = []
    for model, condition in (
        (User, (User.pending_expires_at <= now) & User.email_verified.is_(False)),
        (AuthActionToken, AuthActionToken.expires_at <= now),
        (AuthSession, AuthSession.expires_at <= now),
        (AuthOAuthAttempt, AuthOAuthAttempt.expires_at <= now),
        (AuthRateLimit, AuthRateLimit.expires_at <= now),
    ):
        result = await session.execute(delete(model).where(condition))
        # RETURNING 없는 DELETE는 CursorResult를 반환한다. AsyncSession.execute의
        # 일반 Result 타입에는 PostgreSQL 드라이버의 실제 삭제 건수(rowcount)가 없다.
        deletion_counts.append(cast(CursorResult[tuple[()]], result).rowcount)
    user_count, token_count, session_count, attempt_count, rate_limit_count = (
        deletion_counts
    )
    return user_count, token_count, session_count, attempt_count, rate_limit_count
