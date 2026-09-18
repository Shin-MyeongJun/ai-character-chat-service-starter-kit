# 수동 실행 예제다. 설정된 저장소의 manual/example.txt를 쓰고 읽은 뒤 삭제한다.
"""Run with: python -m app.modules.asset_storage.example"""

from __future__ import annotations

import asyncio
import io

from app.modules.asset_storage import (
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    StoreAssetCommand,
    create_asset_storage_service,
    load_asset_storage_settings,
)


async def main() -> None:
    settings = load_asset_storage_settings()
    payload = b"independent asset_storage example\n"
    object_key = "manual/example.txt"

    async with create_asset_storage_service(settings) as storage:
        stored = await storage.store_asset(
            StoreAssetCommand(
                object_key=object_key,
                content=io.BytesIO(payload),
                size_bytes=len(payload),
                content_type="text/plain; charset=utf-8",
            )
        )
        print(stored)
        print(await storage.get_asset_metadata(GetAssetMetadataCommand(object_key)))
        async with await storage.read_asset(ReadAssetCommand(object_key)) as opened:
            print((await opened.read()).decode("utf-8"), end="")
        await storage.delete_asset(DeleteAssetCommand(object_key))


if __name__ == "__main__":
    asyncio.run(main())
