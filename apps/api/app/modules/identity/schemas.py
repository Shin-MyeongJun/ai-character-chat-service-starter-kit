"""최소 식별정보만 공개하는 인증 HTTP DTO. 비밀 값의 repr와 추가 필드를 차단한다."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CredentialsRequestDto(AuthRequestDto):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128, repr=False)


class EmailRequestDto(AuthRequestDto):
    email: str = Field(min_length=3, max_length=254)


class TokenRequestDto(AuthRequestDto):
    token: str = Field(min_length=32, max_length=256, repr=False)


class ResetPasswordRequestDto(TokenRequestDto):
    password: str = Field(min_length=12, max_length=128, repr=False)


class GoogleStartRequestDto(AuthRequestDto):
    redirect: str = Field(default="/", max_length=1024)


class AuthUserResponseDto(BaseModel):
    id: UUID
    email: str
    email_verified: bool


class AuthMessageResponseDto(BaseModel):
    message: str = (
        "요청을 처리했습니다. 대상 계정이 처리 가능하면 이메일을 확인해 주세요."
    )


class CSRFResponseDto(BaseModel):
    csrf_token: str


class GoogleStartResponseDto(BaseModel):
    authorization_url: str


class AuthErrorDetailDto(BaseModel):
    code: str


class AuthErrorResponseDto(BaseModel):
    error: AuthErrorDetailDto
