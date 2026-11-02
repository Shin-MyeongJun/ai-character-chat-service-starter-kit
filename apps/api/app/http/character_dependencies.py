# 이 파일 자체는 503 훅이다. main.create_app은 DB·쿠키 인증·관리자 인가를 연결한다.
# 검수 권한도 현재 DB가 지원하는 활성 admin에게만 부여한다.
"""Integration points for the character HTTP adapter.

main supplies FastAPI dependency_overrides for shared DB/auth/role dependencies.
Standalone routers keep rejecting unconfigured hooks.
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
    # main은 검증된 행위자와 최신 DB의 활성 admin을 확인하는 가드로 교체한다.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character administration dependency is not configured.",
    )


async def require_character_moderator() -> None:
    # 검수 역할은 활성 admin으로 제한하며 content 서비스의 소유권 검사는 유지한다.
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Character moderation dependency is not configured.",
    )
