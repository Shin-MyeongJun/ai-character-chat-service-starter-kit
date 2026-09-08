from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.product import Product
from app.modules.content.product import repository
from app.modules.content.product.router import router
from app.modules.content.product.service import command
from app.modules.content.product.types import ProductWrite


def test_unconfigured_identity_fails_closed():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/products/mine').status_code == 503


@pytest.mark.asyncio
async def test_foreign_owner_cannot_update(monkeypatch):
    lookup = AsyncMock(side_effect=LookupError('Product not found.'))
    monkeypatch.setattr(repository, 'owned', lookup)
    async with AsyncSession() as session:
        with pytest.raises(LookupError):
            await command.update_product(session, product_id=uuid4(), owner_id=uuid4(), value=ProductWrite('new'))
        assert not session.in_transaction()
    assert lookup.call_args.kwargs['lock'] is True


@pytest.mark.asyncio
async def test_edit_only_changes_draft(monkeypatch):
    now = datetime.now(UTC)
    entity = Product(id=uuid4(), owner_id=uuid4(), title='old', visibility='private', status='draft', created_at=now, updated_at=now)
    monkeypatch.setattr(repository, 'owned', AsyncMock(return_value=entity))
    monkeypatch.setattr(repository, 'save', AsyncMock(return_value=entity))
    async with AsyncSession() as session:
        result = await command.update_product(session, product_id=entity.id, owner_id=entity.owner_id, value=ProductWrite('new'))
        assert result.title == 'new'
        assert not session.in_transaction()


@pytest.mark.parametrize('value', [ProductWrite(' '), ProductWrite('x', visibility='invalid'), ProductWrite('x', description='x'*20001)])
def test_service_validation(value):
    with pytest.raises(ValueError):
        command.validate_profile(value)
