# 개별 라우터의 기본 훅은 503으로 거절한다. main은 session과 검증된 쿠키 owner 인증을 연결한다.
# 배포에서 authenticate를 명시하면 기존 주입 계약에 따라 owner 의존성을 교체한다.
# errors는 LookupError→404, ValueError→422만 변환하며 다른 오류는 전달한다.
"""Override with shared identity/DB dependencies at application composition time."""

from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def get_product_session() -> AsyncSession:
    raise HTTPException(503, "Product database dependency is not configured.")


async def get_current_owner_id() -> UUID:
    raise HTTPException(503, "Product authentication dependency is not configured.")


async def require_product_admin() -> None:
    raise HTTPException(503, "Product administration dependency is not configured.")


Session = Annotated[AsyncSession, Depends(get_product_session)]
Owner = Annotated[UUID, Depends(get_current_owner_id)]


@contextmanager
def errors():
    try:
        yield
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
