from datetime import datetime
from uuid import UUID
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.modules.content.product.router import Session, Owner, errors
from app.modules.governance.admin.product_policy import set_expiry, moderate_product

router=APIRouter(prefix='/admin/products',tags=['product administration'])


class ExpiryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expires_at: datetime | None
    reason: str = Field(min_length=1,max_length=2000)


class StatusRequest(BaseModel):
    status: Literal['draft','approved','rejected']


@router.put('/versions/{snapshot_id}/expiry')
async def expiry(snapshot_id:UUID,body:ExpiryRequest,session:Session,owner:Owner):
    with errors():
        return await set_expiry(session,snapshot_id=snapshot_id,actor_id=owner,expires_at=body.expires_at,reason=body.reason)


@router.put('/{product_id}/status',status_code=204)
async def status(product_id:UUID,body:StatusRequest,session:Session,owner:Owner):
    with errors():
        await moderate_product(session,product_id=product_id,actor_id=owner,status=body.status)
