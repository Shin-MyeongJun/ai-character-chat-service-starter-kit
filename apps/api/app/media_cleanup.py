# 명시적으로 넘긴 media ID만 정리한다. 참조 여부·보존 시간·저장소 일치는 CharacterMediaService가 검사한다.
# 건별 실패 후 다음 ID를 처리하며 하나라도 예외가 있으면 종료 코드 1을 반환한다.
"""Explicit ID-scoped garbage collection; no bucket/directory enumeration."""

import argparse
import asyncio
import os
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.asset_storage.service import (
    create_asset_storage_service,
    load_asset_storage_settings,
)
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.character.types import CleanupCharacterMediaCommand


async def run_cleanup(media_ids, cutoff):
    settings = load_asset_storage_settings()
    configured = (
        settings.test_local if settings.storage_kind == "test_local" else settings.s3
    )
    engine = create_async_engine(os.environ["DATABASE_URL"])
    failed = False
    try:
        async with create_asset_storage_service(settings) as storage:
            service = CharacterMediaService(
                async_sessionmaker(engine, expire_on_commit=False),
                storage,
                storage_kind=str(settings.storage_kind),
                storage_id=configured.storage_id,
            )
            for media_id in media_ids:
                try:
                    result = await service.cleanup_character_media(
                        CleanupCharacterMediaCommand(media_id, cutoff)
                    )
                    print(f"{media_id}: {result.reason}")
                except Exception as exc:  # noqa: BLE001 - preserve partial failure and nonzero exit
                    # Continue explicit IDs but return failure; DB intent stays retryable.
                    failed = True
                    print(f"{media_id}: failed ({type(exc).__name__})")
    finally:
        await engine.dispose()
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-id", type=UUID, action="append", required=True)
    parser.add_argument("--older-than", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run_cleanup(args.media_id, args.older_than)))


if __name__ == "__main__":
    main()
