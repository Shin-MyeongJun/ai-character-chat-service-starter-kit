from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product.dependencies import (
    get_current_owner_id,
    get_product_session,
)

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
