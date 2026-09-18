"""HTTP DTO와 인증 Command/Info 사이의 순수 변환."""

from app.modules.identity import schemas as Schemas
from app.modules.identity import types as Types


def credentials_request_to_command(
    value: Schemas.CredentialsRequestDto,
) -> Types.CredentialsCommand:
    return Types.CredentialsCommand(value.email, value.password)


def email_request_to_command(value: Schemas.EmailRequestDto) -> Types.EmailCommand:
    return Types.EmailCommand(value.email)


def token_request_to_command(value: Schemas.TokenRequestDto) -> Types.TokenCommand:
    return Types.TokenCommand(value.token)


def reset_request_to_command(
    value: Schemas.ResetPasswordRequestDto,
) -> Types.ResetPasswordCommand:
    return Types.ResetPasswordCommand(value.token, value.password)


def google_request_to_command(
    value: Schemas.GoogleStartRequestDto,
) -> Types.GoogleStartCommand:
    return Types.GoogleStartCommand(value.redirect)


def user_info_to_response(value: Types.UserInfo) -> Schemas.AuthUserResponseDto:
    return Schemas.AuthUserResponseDto(
        id=value.id, email=value.email, email_verified=value.email_verified
    )
