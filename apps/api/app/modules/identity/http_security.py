"""쿠키·CSRF·오류 표현만 담당하는 HTTP 경계. 업무 상태 판단은 서비스에서 수행한다."""

import hmac
import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware

from app.modules.identity import types as Types

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ERROR_STATUS = {
    "invalid_credentials": 401,
    "invalid_token": 401,
    "invalid_session": 401,
    "refresh_reused": 401,
    "csrf_failed": 403,
    "origin_forbidden": 403,
    "account_conflict": 409,
    "invalid_input": 422,
    "invalid_action_token": 400,
    "invalid_google_login": 400,
    "invalid_redirect": 400,
    "rate_limited": 429,
    "mail_unavailable": 503,
    "google_not_configured": 503,
    "auth_not_configured": 503,
}


def get_authentication(request):
    service = getattr(request.app.state, "authentication", None)
    if service is None:
        raise Types.AuthError("auth_not_configured")
    return service


def set_cookie(response, settings, kind, value, max_age):
    response.set_cookie(
        settings.cookie_name(kind),
        value,
        max_age=max_age,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def delete_cookie(response, settings, kind):
    response.delete_cookie(
        settings.cookie_name(kind),
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


def set_session_cookies(response, settings, login):
    remaining = max(0, int((login.expires_at - datetime.now(UTC)).total_seconds()))
    set_cookie(
        response,
        settings,
        "access",
        login.access_token,
        min(settings.access_seconds, remaining),
    )
    set_cookie(response, settings, "refresh", login.refresh_token, remaining)


def clear_session_cookies(response, settings):
    for kind in ("access", "refresh", "csrf", "flow"):
        delete_cookie(response, settings, kind)


def issue_csrf_token(service):
    return service.codec.encode_token(
        kind="csrf",
        subject=str(uuid4()),
        session_id=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def verify_csrf(request, service):
    if request.method in SAFE_METHODS:
        return
    # Origin 없는 상태 변경도 거절한다. 비브라우저 클라이언트 역시 명시적으로 보내야 한다.
    if request.headers.get("origin") not in service.settings.allowed_origins:
        raise Types.AuthError("origin_forbidden")
    cookie = request.cookies.get(service.settings.cookie_name("csrf"), "")
    header = request.headers.get("x-csrf-token", "")
    if (
        not cookie
        or not header
        or not hmac.compare_digest(cookie.encode(), header.encode())
    ):
        raise Types.AuthError("csrf_failed")
    try:
        service.codec.decode_token(header, "csrf")
    except Types.AuthError as exc:
        raise Types.AuthError("csrf_failed") from exc


def error_response(error, request):
    response = JSONResponse(
        {"error": {"code": error.code}}, status_code=ERROR_STATUS.get(error.code, 400)
    )
    response.headers.update(
        {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
    )
    if error.code == "rate_limited":
        response.headers["Retry-After"] = "900"
    service = getattr(request.app.state, "authentication", None)
    if service is not None and error.code in {
        "invalid_token",
        "invalid_session",
        "refresh_reused",
    }:
        clear_session_cookies(response, service.settings)
    if service is not None and request.url.path == "/auth/google/callback":
        delete_cookie(response, service.settings, "flow")
    return response


class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def protected_handler(request: Request):
            try:
                service = get_authentication(request)
                # 프록시 헤더를 직접 신뢰하지 않는다. 배포 시 Uvicorn trusted proxy만 설정한다.
                address = request.client.host if request.client else "unknown"
                await service.check_rate_limit(
                    Types.RateLimitCommand("http", address, 120, 60)
                )
                if (
                    request.method not in SAFE_METHODS
                    or request.url.path == "/auth/google/callback"
                ):
                    await service.check_rate_limit(
                        Types.RateLimitCommand(request.url.path, address, 20, 300)
                    )
                verify_csrf(request, service)
                response = await handler(request)
            except RequestValidationError:
                # FastAPI 기본 422의 input 필드에 비밀번호/토큰 원문이 반사되는 것을 막는다.
                response = error_response(Types.AuthError("invalid_input"), request)
            except Types.AuthError as exc:
                response = error_response(exc, request)
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                }
            )
            return response

        return protected_handler


class CookieCSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        service = getattr(request.app.state, "authentication", None)
        if (
            service is not None
            and request.method not in SAFE_METHODS
            and any(
                service.settings.cookie_name(kind) in request.cookies
                for kind in ("access", "refresh")
            )
        ):
            try:
                verify_csrf(request, service)
            except Types.AuthError as exc:
                return error_response(exc, request)
        return await call_next(request)


class AuthAccessLogFilter(logging.Filter):
    """기본 Uvicorn access logger에도 OAuth code/state 쿼리가 남지 않도록 제거한다."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, target, version, status = record.args
            if isinstance(target, str) and target.split("?", 1)[0].startswith("/auth/"):
                record.args = (client, method, target.split("?", 1)[0], version, status)
        return True
