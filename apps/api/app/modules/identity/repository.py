# 사용자 기본키로 한 행을 읽는다. role/status 판정은 service/query.require_admin에 있다.
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import User


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)
