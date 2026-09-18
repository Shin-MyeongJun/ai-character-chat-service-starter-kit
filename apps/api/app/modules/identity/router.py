"""인증 API 전용 라우터. 쿠키 전달과 DTO 변환만 수행하고 DB를 직접 다루지 않는다."""

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.modules.identity import schemas as Schemas
from app.modules.identity import types as Types
from app.modules.identity.http_security import (
    AuthRoute,
    clear_session_cookies,
    delete_cookie,
    get_authentication,
    issue_csrf_token,
    set_cookie,
    set_session_cookies,
)
from app.modules.identity.mapper import schema as SchemaMapper

router = APIRouter(
    prefix="/auth",
    tags=["authentication"],
    route_class=AuthRoute,
    responses={
        status: {"model": Schemas.AuthErrorResponseDto}
        for status in (400, 401, 403, 409, 422, 429, 503)
    },
)


@router.get("/csrf", response_model=Schemas.CSRFResponseDto)
async def get_csrf(request: Request, response: Response):
    service = get_authentication(request)
    token = issue_csrf_token(service)
    set_cookie(response, service.settings, "csrf", token, 3600)
    return Schemas.CSRFResponseDto(csrf_token=token)


@router.post(
    "/register", status_code=202, response_model=Schemas.AuthMessageResponseDto
)
async def register_user(body: Schemas.CredentialsRequestDto, request: Request):
    await get_authentication(request).register_user(
        SchemaMapper.credentials_request_to_command(body)
    )
    return Schemas.AuthMessageResponseDto()


@router.post(
    "/email/resend", status_code=202, response_model=Schemas.AuthMessageResponseDto
)
async def resend_email(body: Schemas.EmailRequestDto, request: Request):
    await get_authentication(request).resend_verification(
        SchemaMapper.email_request_to_command(body)
    )
    return Schemas.AuthMessageResponseDto()


@router.post("/email/verify", response_model=Schemas.AuthUserResponseDto)
async def verify_email(body: Schemas.TokenRequestDto, request: Request):
    return SchemaMapper.user_info_to_response(
        await get_authentication(request).verify_email(
            SchemaMapper.token_request_to_command(body)
        )
    )


@router.post(
    "/password/reset/request",
    status_code=202,
    response_model=Schemas.AuthMessageResponseDto,
)
async def request_password_reset(body: Schemas.EmailRequestDto, request: Request):
    await get_authentication(request).request_password_reset(
        SchemaMapper.email_request_to_command(body)
    )
    return Schemas.AuthMessageResponseDto()


@router.post("/password/reset", status_code=204)
async def reset_password(body: Schemas.ResetPasswordRequestDto, request: Request):
    service = get_authentication(request)
    await service.reset_password(SchemaMapper.reset_request_to_command(body))
    response = Response(status_code=204)
    clear_session_cookies(response, service.settings)
    return response


@router.post("/login", response_model=Schemas.AuthUserResponseDto)
async def login_user(
    body: Schemas.CredentialsRequestDto, request: Request, response: Response
):
    service = get_authentication(request)
    login = await service.login_user(SchemaMapper.credentials_request_to_command(body))
    set_session_cookies(response, service.settings, login)
    return SchemaMapper.user_info_to_response(login.user)


@router.post("/refresh", response_model=Schemas.AuthUserResponseDto)
async def refresh_session(request: Request, response: Response):
    service = get_authentication(request)
    login = await service.refresh_session(
        Types.TokenCommand(
            request.cookies.get(service.settings.cookie_name("refresh"), "")
        )
    )
    set_session_cookies(response, service.settings, login)
    return SchemaMapper.user_info_to_response(login.user)


@router.post("/logout", status_code=204)
async def logout_session(request: Request):
    service = get_authentication(request)
    await service.logout_session(
        Types.LogoutCommand(
            request.cookies.get(service.settings.cookie_name("refresh"), ""),
            request.cookies.get(service.settings.cookie_name("access"), ""),
        )
    )
    response = Response(status_code=204)
    clear_session_cookies(response, service.settings)
    return response


@router.post("/logout-all", status_code=204)
async def logout_all_sessions(request: Request):
    service = get_authentication(request)
    await service.logout_all_sessions(
        Types.TokenCommand(
            request.cookies.get(service.settings.cookie_name("access"), "")
        )
    )
    response = Response(status_code=204)
    clear_session_cookies(response, service.settings)
    return response


@router.get("/me", response_model=Schemas.AuthUserResponseDto)
async def get_current_user(request: Request):
    service = get_authentication(request)
    user = await service.get_authenticated_user(
        Types.TokenCommand(
            request.cookies.get(service.settings.cookie_name("access"), "")
        )
    )
    return SchemaMapper.user_info_to_response(user)


@router.post("/google/start", response_model=Schemas.GoogleStartResponseDto)
async def start_google_login(
    body: Schemas.GoogleStartRequestDto, request: Request, response: Response
):
    info = await request.app.state.google_login.start_google_login(
        SchemaMapper.google_request_to_command(body)
    )
    set_cookie(response, get_authentication(request).settings, "flow", info.cookie, 600)
    return Schemas.GoogleStartResponseDto(authorization_url=info.url)


@router.get("/google/callback", response_class=RedirectResponse, status_code=303)
async def complete_google_login(
    request: Request,
    state: str = Query(default="", max_length=256),
    code: str = Query(default="", max_length=4096),
):
    service = get_authentication(request)
    if not state or not code:
        raise Types.AuthError("invalid_google_login")
    info = await request.app.state.google_login.complete_google_login(
        Types.GoogleCallbackCommand(
            state, code, request.cookies.get(service.settings.cookie_name("flow"), "")
        )
    )
    response = RedirectResponse(info.redirect, status_code=303)
    set_session_cookies(response, service.settings, info.login)
    delete_cookie(response, service.settings, "flow")
    return response
