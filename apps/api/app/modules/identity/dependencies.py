"""HTTP 인증 의존성 연결. 검증된 내부 UUID만 기존 owner 훅에 제공한다."""

from typing import cast
from uuid import UUID

from fastapi import Request

from app.modules.identity import types as Types
from app.modules.identity.http_security import get_authentication, verify_csrf
from app.modules.identity.service.workflow.google import GoogleLoginService
from app.modules.identity.service.workflow.mail import AuthenticationMailWorkflow


def get_authentication_mail(request: Request) -> AuthenticationMailWorkflow:
    # main installs this workflow with authentication; preserve direct attribute
    # lookup failures for incomplete application composition.
    return cast(AuthenticationMailWorkflow, request.app.state.authentication_mail)


def get_google_login(request: Request) -> GoogleLoginService:
    # Same composition boundary as the mail workflow, without a new fallback.
    return cast(GoogleLoginService, request.app.state.google_login)


async def get_verified_user_id(request: Request) -> UUID:
    service = get_authentication(request)
    verify_csrf(request, service)
    user = await service.get_authenticated_user(
        Types.TokenCommand(
            request.cookies.get(service.settings.cookie_name("access"), "")
        )
    )
    return user.id
