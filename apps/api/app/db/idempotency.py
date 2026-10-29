# 행 생성 전에도 namespace:key의 해시로 PostgreSQL 트랜잭션 advisory lock을 잡는다.
# 동일 키 요청을 직렬화할 뿐 결과 재사용·내용 충돌 검사는 각 서비스가 수행한다.
import hashlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_key(session: AsyncSession, namespace: str, key: str) -> None:
    """Stable transaction advisory lock, including when the row does not exist yet."""
    digest = hashlib.sha256(f"{namespace}:{key}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
