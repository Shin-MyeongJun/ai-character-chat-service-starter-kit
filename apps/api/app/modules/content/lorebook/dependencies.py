"""Integration hooks for the lorebook HTTP adapter.

The application can replace these with FastAPI dependency overrides until
shared database and authentication dependencies are available.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession


async def get_lorebook_session() -> AsyncSession:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Lorebook database dependency is not configured.",
    )


async def get_current_owner_id() -> UUID:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Lorebook authentication dependency is not configured.",
    )


async def require_lorebook_admin() -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Lorebook administration dependency is not configured.",
    )


async def require_lorebook_moderator() -> None:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Lorebook moderation dependency is not configured.",
    )
