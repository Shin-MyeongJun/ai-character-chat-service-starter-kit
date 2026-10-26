# 만료 시각과 현재 시각의 경계, 무기한 버전을 확인한다.
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service.query import ensure_available


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
