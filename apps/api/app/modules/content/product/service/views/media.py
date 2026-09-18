# 상품 접근·버전 만료·상품 소속을 확인한 뒤 그 버전 캐릭터 스냅샷에 연결된 미디어만 읽는다.
from app.db.transaction import use_case_transaction
from app.modules.asset_storage import types as AssetStorageTypes
from app.modules.content.character import types as CharacterTypes
from app.modules.content.character.service.media import CharacterMediaService
from app.modules.content.product import types as Types
from app.modules.content.product.service import query as QueryService


class ProductMediaService:
    def __init__(self, sessions, media: CharacterMediaService):
        self.sessions = sessions
        self.media = media

    async def read_product_media(
        self, command: Types.ReadProductMediaCommand
    ) -> AssetStorageTypes.AssetReadInfo:
        async with self.sessions() as session, use_case_transaction(session):
            await QueryService.get_accessible_product(
                session,
                Types.GetAccessibleProductCommand(
                    product_id=command.product_id,
                    user_id=command.user_id,
                ),
            )
            snapshot = await QueryService.ensure_snapshot_available(
                session, Types.ProductSnapshotCommand(command.snapshot_id)
            )
            if snapshot.product_id != command.product_id:
                raise LookupError("Version not found.")
            composition = await QueryService.get_snapshot_composition(
                session, Types.ProductSnapshotCommand(command.snapshot_id)
            )
        return await self.media.read_snapshot_media(
            CharacterTypes.ReadSnapshotMediaCommand(
                media_id=command.media_id,
                snapshot_ids=tuple(
                    c.character_snapshot_id for c in composition.characters
                ),
            )
        )
