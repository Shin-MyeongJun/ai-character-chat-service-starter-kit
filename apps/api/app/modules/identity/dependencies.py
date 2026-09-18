"""HTTP 인증 의존성 연결. 검증된 내부 UUID만 기존 owner 훅에 제공한다."""

from uuid import UUID

from fastapi import Request

from app.modules.identity import types as Types
from app.modules.identity.http_security import get_authentication, verify_csrf


async def get_verified_user_id(request: Request) -> UUID:
    service = get_authentication(request)
    verify_csrf(request, service)
    user = await service.get_authenticated_user(
        Types.TokenCommand(
            request.cookies.get(service.settings.cookie_name("access"), "")
        )
    )
    return user.id
