from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product.dependencies import get_current_owner_id, get_product_session
from app.modules.content.product.mapper.schema import to_write
from app.modules.content.product.schemas import ProductRequest
from app.modules.content.product.service import command, query
from app.modules.content.product.types import ProductInfo
from app.modules.content.product.types import Composition
from app.modules.content.product.service import composition
from app.modules.content.product.service import settings
from app.modules.content.product.service import releases

router = APIRouter(prefix="/products", tags=["products"])
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


@router.get("/mine", response_model=list[ProductInfo])
async def list_mine(session: Session, owner: Owner, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return await query.list_products(session, owner_id=owner, offset=offset, limit=limit)


@router.post("", response_model=ProductInfo, status_code=201)
async def create(body: ProductRequest, session: Session, owner: Owner):
    with errors():
        return await command.create_product(session, owner_id=owner, value=to_write(body))


@router.get("/{product_id}/draft", response_model=ProductInfo)
async def get_draft(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return await query.get_product(session, product_id=product_id, owner_id=owner)


@router.put("/{product_id}/draft", response_model=ProductInfo)
async def update(product_id: UUID, body: ProductRequest, session: Session, owner: Owner):
    with errors():
        return await command.update_product(session, product_id=product_id, owner_id=owner, value=to_write(body))


@router.delete("/{product_id}/draft", status_code=204)
async def delete(product_id: UUID, session: Session, owner: Owner):
    with errors():
        await command.delete_product(session, product_id=product_id, owner_id=owner)


@router.put("/{product_id}/composition", response_model=Composition)
async def put_composition(product_id: UUID, body: Composition, session: Session, owner: Owner):
    with errors():
        return await composition.replace_composition(session, product_id=product_id, owner_id=owner, value=body)


@router.get("/{product_id}/composition", response_model=Composition)
async def read_composition(product_id: UUID, session: Session, owner: Owner):
    with errors():
        return await composition.get_composition(session, product_id=product_id, owner_id=owner)


@router.put("/{product_id}/settings", response_model=settings.Settings)
async def put_settings(product_id: UUID, body: settings.Settings, session: Session, owner: Owner):
    with errors():
        return await settings.set_settings(session, product_id=product_id, owner_id=owner, value=body)


@router.post("/{product_id}/releases", response_model=releases.ReleaseInfo, status_code=201)
async def publish(product_id: UUID, body: releases.ReleaseRequest, session: Session, owner: Owner):
    with errors():
        return await releases.publish(session,product_id=product_id,owner_id=owner,value=body)


@router.patch("/{product_id}/releases/{snapshot_id}/note", response_model=releases.ReleaseInfo)
async def correct_note(product_id: UUID, snapshot_id: UUID, body: releases.ReleaseRequest, session: Session, owner: Owner):
    with errors():
        if body.auto_apply_media:
            raise HTTPException(422,'Patch corrections cannot change update policy.')
        return await releases.correct_note(session,product_id=product_id,snapshot_id=snapshot_id,owner_id=owner,summary=body.summary,body=body.body)
