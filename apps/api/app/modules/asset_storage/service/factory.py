# 앱 시작 시 선택한 저장소의 어댑터 하나를 만든다. 요청마다 클라이언트를 새로 만들지 않는다.
from __future__ import annotations

from typing import Any

from app.modules.asset_storage.adapters import S3StorageAdapter, TestLocalStorageAdapter
from app.modules.asset_storage.service.storage import AssetStorageService
from app.modules.asset_storage.types import (
    AssetStorageAdapter,
    AssetStorageConfigurationError,
    AssetStorageSettings,
    StorageKind,
)


def create_asset_storage_service(
    settings: AssetStorageSettings,
    *,
    s3_client: Any | None = None,
) -> AssetStorageService:
    """Create one adapter/client for application composition, not per request."""

    adapter: AssetStorageAdapter
    if settings.storage_kind is StorageKind.TEST_LOCAL:
        if s3_client is not None:
            raise AssetStorageConfigurationError(
                "s3_client cannot be supplied for test_local storage."
            )
        if settings.test_local is None:  # guarded by typed settings
            raise AssetStorageConfigurationError("test_local settings are missing.")
        adapter = TestLocalStorageAdapter(settings.test_local)
    elif settings.storage_kind is StorageKind.S3:
        if settings.s3 is None:  # guarded by typed settings
            raise AssetStorageConfigurationError("S3 settings are missing.")
        adapter = S3StorageAdapter(settings.s3, client=s3_client)
    else:  # pragma: no cover - StorageKind makes this unreachable
        raise AssetStorageConfigurationError(
            f"Unsupported asset storage kind: {settings.storage_kind!r}."
        )
    return AssetStorageService(adapter)
