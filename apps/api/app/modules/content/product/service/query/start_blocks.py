from uuid import UUID

from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper


def get_snapshot_start_blocks(
    snapshot: Types.ProductSnapshotInfo, start_set_id: UUID
) -> tuple[Types.ContentBlockInfo, ...] | None:
    for start in snapshot.snapshot_data.get("starts", []):
        if start["start_set_id"] == str(start_set_id):
            blocks = start["content_blocks"]
            if not isinstance(blocks, list):
                raise ValueError("Invalid published start blocks.")
            return tuple(
                PersistenceMapper.content_block_json_to_info(block) for block in blocks
            )
    return None
