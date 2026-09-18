# 명시적 opt-in과 PostgreSQL이 필요한 실제 S3 왕복 테스트. 생성한 요청의 객체만 finally에서 삭제한다.
"""Opt-in managed-media smoke test; only its unique test prefix is cleaned."""

import io
import os
from uuid import uuid4

import pytest
from app.db.models.character_media import CharacterMedia
from app.db.transaction import use_case_transaction
from app.modules.asset_storage.service import create_asset_storage_service
from app.modules.asset_storage.types import (
    AssetStorageSettings,
    DeleteAssetCommand,
    ExecutionEnvironment,
    S3StorageSettings,
    StorageKind,
)
from app.modules.content.character import types as Types
from app.modules.content.character.service.media import CharacterMediaService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_product_integration import seed


@pytest.mark.asyncio
async def test_real_s3_managed_upload_retry_read(db):
    if os.getenv("RUN_ASSET_STORAGE_S3_INTEGRATION") != "1":
        pytest.skip("Explicit RUN_ASSET_STORAGE_S3_INTEGRATION=1 required.")
    configured = S3StorageSettings(
        storage_id=os.environ["ASSET_STORAGE_ID"],
        bucket=os.environ["ASSET_S3_BUCKET"],
        region=os.environ["ASSET_S3_REGION"],
        key_prefix="/".join(
            filter(
                None,
                [os.getenv("ASSET_S3_KEY_PREFIX", ""), "cod-integration", uuid4().hex],
            )
        ),
    )
    settings = AssetStorageSettings(
        environment=ExecutionEnvironment.TEST,
        storage_kind=StorageKind.S3,
        s3=configured,
    )
    owner, character, _ = await seed(db)
    request_id = uuid4()
    value = Types.UploadCharacterMediaCommand(
        character.id,
        owner.id,
        request_id,
        io.BytesIO(b"test media"),
        "image/png",
        "test.png",
        "test",
    )
    async with create_asset_storage_service(settings) as storage:
        service = CharacterMediaService(
            async_sessionmaker(db.bind, expire_on_commit=False),
            storage,
            storage_kind="s3",
            storage_id=configured.storage_id,
        )
        try:
            first = await service.upload_character_media(value)
            assert (await service.upload_character_media(value)).id == first.id
            async with await service.read_character_media(
                Types.ReadCharacterMediaCommand(first.id, owner.id)
            ) as opened:
                assert await opened.read() == b"test media"
        finally:
            # Even after a finalize failure, only this request's reserved object
            # beneath the freshly generated S3 prefix can be deleted.
            async with use_case_transaction(db):
                key = await db.scalar(
                    select(CharacterMedia.object_key).where(
                        CharacterMedia.request_id == request_id
                    )
                )
            if key is not None:
                await storage.delete_asset(DeleteAssetCommand(key))
