# 이 파일 자체는 503 훅이다. 현재 main.create_app은 DB 훅을 실제 세션으로 교체한다.
# owner 인증은 주입 시에만 연결되고 admin/moderator 가드는 기본 앱에서 교체하지 않는다.
"""Integration points for the character HTTP adapter.

TODO: Replace these hooks with shared DB/auth dependencies when those modules
exist. Until then the application can supply FastAPI dependency_overrides.
Unconfigured hooks reject requests instead of inventing an authenticated owner.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


async def get_character_session() -> AsyncSession:
    """Supply a request-scoped session and close it when the request ends."""
    # TODO: Wire a yielding session dependency. Commands need a fresh session with
    # no active transaction; do not share a session already used by authentication.
    # TODO(error-codes): Use the shared infrastructure-unavailable response later.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character database dependency is not configured.",
    )


async def get_current_owner_id() -> UUID:
    # TODO: Resolve the authenticated user's ID through the identity module.
    # Never treat a raw request owner_id or an unverified header as authentication.
    # TODO(error-codes): Replace with shared unauthenticated/expired-token handling.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character authentication dependency is not configured.",
    )


async def require_character_admin() -> None:
    # TODO: Authenticate and authorize cross-owner/private-character reads.
    # TODO(error-codes): Use the shared authentication/authorization error codes.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character administration dependency is not configured.",
    )


async def require_character_moderator() -> None:
    # TODO: Authenticate and authorize moderation separately from ownership.
    # TODO(error-codes): Use the shared authentication/authorization error codes.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character moderation dependency is not configured.",
    )
