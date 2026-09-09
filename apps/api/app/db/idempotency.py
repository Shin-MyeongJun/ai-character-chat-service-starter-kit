import hashlib

from sqlalchemy import text


async def lock_key(session, namespace: str, key: str):
    """Stable transaction advisory lock, including when the row does not exist yet."""
    digest = hashlib.sha256(f"{namespace}:{key}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
