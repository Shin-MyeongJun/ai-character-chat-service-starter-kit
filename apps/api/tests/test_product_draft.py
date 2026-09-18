# 미설정 인증 거절, 타인 수정 거절, 초안 변경과 발행본 분리, 입력 검증을 확인한다.
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.db.models.product import Product
from app.modules.content.product import repository
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.repository import core as CoreRepository
from app.modules.content.product.router import router
from app.modules.content.product.service import command
from app.modules.content.product.types import ProductProfileCommand
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession


def test_unconfigured_identity_fails_closed():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/products/mine").status_code == 503


@pytest.mark.asyncio
async def test_foreign_owner_cannot_update(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(repository, "get_owned_product", lookup)
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await command.update_product(
                session,
                ProductTypes.UpdateProductCommand(
                    product_id=uuid4(),
                    owner_id=uuid4(),
                    value=ProductProfileCommand("new"),
                ),
            )
        assert not session.in_transaction()
    assert lookup.call_args.kwargs["lock"] is True


@pytest.mark.asyncio
async def test_edit_only_changes_draft(monkeypatch):
    now = datetime.now(UTC)
    entity = Product(
        id=uuid4(),
        owner_id=uuid4(),
        title="old",
        visibility="private",
        status="draft",
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(repository, "get_owned_product", AsyncMock(return_value=entity))
    monkeypatch.setattr(
        CoreRepository, "get_owned_product", AsyncMock(return_value=entity)
    )
    monkeypatch.setattr(CoreRepository, "save_product", AsyncMock(return_value=entity))
    async with AsyncSession() as session:
        result = await command.update_product(
            session,
            ProductTypes.UpdateProductCommand(
                product_id=entity.id,
                owner_id=entity.owner_id,
                value=ProductProfileCommand("new"),
            ),
        )
        assert result.title == "new"
        assert not session.in_transaction()


@pytest.mark.parametrize(
    "value",
    [
        ProductProfileCommand(" "),
        ProductProfileCommand("x", visibility="invalid"),
        ProductProfileCommand("x", description="x" * 20001),
    ],
)
def test_service_validation(value):
    with pytest.raises(ValueError):
        command.validate_profile(value)
