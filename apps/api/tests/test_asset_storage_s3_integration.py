from __future__ import annotations

import io
import os
from uuid import uuid4

import pytest
from app.modules.asset_storage import (
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    S3StorageSettings,
    StoreAssetCommand,
)
from app.modules.asset_storage.adapters import S3StorageAdapter

pytestmark = pytest.mark.asyncio


async def test_real_s3_round_trip_under_unique_prefix():
    if os.getenv("RUN_ASSET_STORAGE_S3_INTEGRATION") != "1":
        pytest.skip("Set RUN_ASSET_STORAGE_S3_INTEGRATION=1 for real S3 verification.")
    bucket = os.getenv("ASSET_S3_BUCKET", "").strip()
    region = os.getenv("ASSET_S3_REGION", "").strip()
    storage_id = os.getenv("ASSET_STORAGE_ID", "").strip()
    if not bucket or not region or not storage_id:
        pytest.fail("ASSET_S3_BUCKET, ASSET_S3_REGION, and ASSET_STORAGE_ID are required.")

    configured_prefix = os.getenv("ASSET_S3_KEY_PREFIX", "").strip()
    unique_prefix = "/".join(
        part for part in (configured_prefix, "cod-integration", uuid4().hex) if part
    )
    adapter = S3StorageAdapter(
        S3StorageSettings(
            storage_id=storage_id,
            bucket=bucket,
            region=region,
            key_prefix=unique_prefix,
            max_attempts=int(os.getenv("ASSET_S3_MAX_ATTEMPTS", "3")),
        )
    )
    key = "round-trip.bin"
    payload = b"asset-storage-integration"
    try:
        await adapter.store_asset(
            StoreAssetCommand(key, io.BytesIO(payload), len(payload), "application/test")
        )
        metadata = await adapter.get_asset_metadata(GetAssetMetadataCommand(key))
        assert metadata.size_bytes == len(payload)
        assert metadata.content_type == "application/test"
        async with await adapter.read_asset(ReadAssetCommand(key)) as opened:
            assert await opened.read() == payload
    finally:
        # This test deletes only its one object beneath its UUID-owned prefix.
        await adapter.delete_asset(DeleteAssetCommand(key))
        await adapter.aclose()
