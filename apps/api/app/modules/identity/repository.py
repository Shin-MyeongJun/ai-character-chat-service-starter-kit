# 인증 테이블 조회·쓰기와 PostgreSQL 잠금을 담당한다. 상태 판단과 commit은 서비스 소유다.
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
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


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def lock_identity(session, key: str) -> None:
    # 행 생성 전에도 동일 이메일/Google sub의 경합을 직렬화한다.
    await lock_key(session, "identity", key)


async def get_user_by_email(session, email: str) -> User | None:
    return await session.scalar(
        select(User).where(User.email == email).with_for_update()
    )


async def get_locked_user(session, user_id: UUID) -> User | None:
    return await session.scalar(
        select(User).where(User.id == user_id).with_for_update()
    )


async def get_google_user(session, sub: str) -> User | None:
    return await session.scalar(
        select(User)
        .join(UserOAuthAccount, User.id == UserOAuthAccount.user_id)
        .where(
            UserOAuthAccount.provider == "google",
            UserOAuthAccount.provider_user_id == sub,
        )
        .with_for_update(of=User)
    )


async def create_user(
    session, *, user_id, email, password_hash, verified, pending_expires_at
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


async def create_google_account(session, user_id, sub) -> None:
    await session.execute(
        insert(UserOAuthAccount).values(
            user_id=user_id, provider="google", provider_user_id=sub
        )
    )


async def verify_user_email(session, user_id) -> User:
    return (
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(email_verified=True, pending_expires_at=None)
            .returning(User)
        )
    ).scalar_one()


async def update_password(session, user_id, password_hash) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(password_hash=password_hash)
    )


async def delete_pending_user(session, user_id) -> None:
    await session.execute(
        delete(User).where(
            User.id == user_id,
            User.email_verified.is_(False),
            User.pending_expires_at.is_not(None),
        )
    )


async def create_session(
    session, *, session_id, user_id, refresh_hash, now, expires_at
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


async def get_session(session, session_id) -> AuthSession | None:
    return await session.scalar(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )


async def rotate_session(session, session_id, refresh_hash) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(refresh_hash=refresh_hash)
    )


async def revoke_session(session, session_id, now) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke_user_sessions(session, user_id, now) -> None:
    await session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def invalidate_action_tokens(session, user_id, purpose, now) -> None:
    statement = update(AuthActionToken).where(
        AuthActionToken.user_id == user_id, AuthActionToken.consumed_at.is_(None)
    )
    if purpose is not None:
        statement = statement.where(AuthActionToken.purpose == purpose)
    await session.execute(statement.values(consumed_at=now))


async def create_action_token(
    session, *, user_id, token_hash, purpose, expires_at
) -> None:
    await session.execute(
        insert(AuthActionToken).values(
            user_id=user_id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
    )


async def get_action_token(session, token_hash) -> AuthActionToken | None:
    # 사용자 ID를 먼저 읽고 사용자 → 토큰 순서로 잠근다. 재설정/로그인 사이 교착을 피한다.
    return await session.scalar(
        select(AuthActionToken).where(AuthActionToken.token_hash == token_hash)
    )


async def consume_action_token(session, token_id, now) -> UUID | None:
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


async def create_oauth_attempt(session, state_hash, expires_at) -> None:
    await session.execute(
        insert(AuthOAuthAttempt).values(state_hash=state_hash, expires_at=expires_at)
    )


async def consume_oauth_attempt(session, state_hash, now) -> str | None:
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


async def increment_rate_limit(session, key, limit, expires_at) -> int | None:
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


async def delete_expired_records(
    session, now: datetime
) -> tuple[int, int, int, int, int]:
    results = []
    for model, condition in (
        (User, (User.pending_expires_at <= now) & User.email_verified.is_(False)),
        (AuthActionToken, AuthActionToken.expires_at <= now),
        (AuthSession, AuthSession.expires_at <= now),
        (AuthOAuthAttempt, AuthOAuthAttempt.expires_at <= now),
        (AuthRateLimit, AuthRateLimit.expires_at <= now),
    ):
        result = await session.execute(delete(model).where(condition))
        results.append(result.rowcount)
    return tuple(results)
