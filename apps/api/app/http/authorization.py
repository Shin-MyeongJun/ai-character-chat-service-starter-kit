"""기존 HTTP 인증 훅을 최신 DB 관리자 인가에 연결한다."""

from collections.abc import Awaitable, Callable
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from app.db.types import SessionFactory
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


def create_admin_dependency(
    owner_dependency: Callable[..., object],
) -> Callable[..., Awaitable[None]]:
    """검증된 행위자 훅을 재사용하되 업무 세션과 인가 조회 세션을 분리한다."""

    async def require_active_admin(
        request: Request,
        actor_id: Annotated[UUID, Depends(owner_dependency)],
    ) -> None:
        # main의 lifespan이 동적 app.state에 SessionFactory를 조립한다.
        session_factory = cast(
            SessionFactory | None,
            getattr(request.app.state, "session_factory", None),
        )
        if session_factory is None:
            raise HTTPException(503, "Administrative authorization is not configured.")
        # 인가 SELECT의 autobegin이 이후 쓰기 유스케이스의 begin과 충돌하지 않는다.
        async with session_factory() as session:
            try:
                await IdentityQueryService.require_admin(
                    session, IdentityTypes.GetUserCommand(user_id=actor_id)
                )
            except LookupError as exc:
                raise HTTPException(403, "forbidden") from exc

    return require_active_admin
