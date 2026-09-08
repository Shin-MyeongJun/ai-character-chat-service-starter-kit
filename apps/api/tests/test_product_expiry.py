from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.governance.admin.product_policy import ensure_available, require_admin


@pytest.mark.asyncio
async def test_expiry_boundary_and_unlimited_version():
    now = datetime.now(UTC)
    snapshot = SimpleNamespace(expires_at=now)
    session = SimpleNamespace(scalar=AsyncMock(return_value=snapshot))
    with pytest.raises(ValueError, match="expired"):
        await ensure_available(session, uuid4(), now=now)
    snapshot.expires_at = now + timedelta(microseconds=1)
    assert await ensure_available(session, uuid4(), now=now) is snapshot
    snapshot.expires_at = None
    assert await ensure_available(session, uuid4(), now=now) is snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("role,status", [("user", "active"), ("admin", "suspended")])
async def test_administration_requires_active_admin(role, status):
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(role=role, status=status))
    )
    with pytest.raises(LookupError):
        await require_admin(session, uuid4())
