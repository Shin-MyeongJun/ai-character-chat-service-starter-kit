# character 미디어 흐름에 저장·읽기·삭제·메타데이터 조회를 제공하는 전달 계층이다.
# 소유권·DB 상태·파일 내용 검증은 이 클래스에서 수행하지 않는다.
from __future__ import annotations

from typing import Self

from app.modules.asset_storage.types import (
    AssetMetadataInfo,
    AssetReadInfo,
    AssetStorageAdapter,
    DeleteAssetCommand,
    GetAssetMetadataCommand,
    ReadAssetCommand,
    StoreAssetCommand,
    StoredAssetInfo,
)


class AssetStorageService:
    """Provider-neutral file storage use cases."""

    def __init__(self, adapter: AssetStorageAdapter) -> None:
        self._adapter = adapter

    async def store_asset(self, command: StoreAssetCommand) -> StoredAssetInfo:
        return await self._adapter.store_asset(command)

    async def read_asset(self, command: ReadAssetCommand) -> AssetReadInfo:
        return await self._adapter.read_asset(command)

    async def delete_asset(self, command: DeleteAssetCommand) -> None:
        await self._adapter.delete_asset(command)

    async def get_asset_metadata(
        self, command: GetAssetMetadataCommand
    ) -> AssetMetadataInfo:
        return await self._adapter.get_asset_metadata(command)

    async def aclose(self) -> None:
        await self._adapter.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
