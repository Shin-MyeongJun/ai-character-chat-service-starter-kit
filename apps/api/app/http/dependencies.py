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
