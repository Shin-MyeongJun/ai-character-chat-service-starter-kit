from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.query import ensure_available
from app.modules.identity.service.query import require_admin
from app.modules.identity.types import GetUserCommand


@pytest.mark.asyncio
async def test_expiry_boundary_and_unlimited_version():
    now = datetime.now(UTC)
    snapshot = SimpleNamespace(
        id=uuid4(),
        product_id=uuid4(),
        version=1,
        snapshot_data={},
        expires_at=now,
        expiry_reason=None,
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=snapshot))
    with pytest.raises(ValueError, match="expired"):
        await ensure_available(
            session, ProductTypes.EnsureAvailableCommand(snapshot_id=uuid4(), now=now)
        )
    snapshot.expires_at = now + timedelta(microseconds=1)
    assert (
        await ensure_available(
            session, ProductTypes.EnsureAvailableCommand(snapshot_id=uuid4(), now=now)
        )
    ).expires_at == snapshot.expires_at
    snapshot.expires_at = None
    assert (
        await ensure_available(
            session, ProductTypes.EnsureAvailableCommand(snapshot_id=uuid4(), now=now)
        )
    ).expires_at == snapshot.expires_at


@pytest.mark.asyncio
@pytest.mark.parametrize("role,status", [("user", "active"), ("admin", "suspended")])
async def test_administration_requires_active_admin(role, status):
    session = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(id=uuid4(), role=role, status=status)
        )
    )
    with pytest.raises(LookupError):
        await require_admin(session, GetUserCommand(uuid4()))
