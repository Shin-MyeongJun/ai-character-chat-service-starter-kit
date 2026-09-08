"""Override with shared identity/DB dependencies at application composition time."""
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession


async def get_product_session() -> AsyncSession:
    raise HTTPException(503, "Product database dependency is not configured.")


async def get_current_owner_id() -> UUID:
    raise HTTPException(503, "Product authentication dependency is not configured.")


async def require_product_admin() -> None:
    raise HTTPException(503, "Product administration dependency is not configured.")
