"""Freeze studio image references within the product publication transaction."""

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.product import types as Types
from app.modules.content.product.service.command.file_versions import (
    retain_product_file_version,
)


async def _freeze_studio_publication_images(
    session: AsyncSession,
    product_id: UUID,
    snapshot_id: UUID,
    images: Types.StudioPublicationImagesInfo,
    character_slot_ids: Mapping[UUID, UUID],
    start_set_ids: Mapping[UUID, UUID],
    lorebook_snapshot_id: UUID,
) -> tuple[list[Types.ProductJsonObject], list[Types.ProductJsonObject]]:
    items: list[Types.ProductJsonObject] = []
    files: set[UUID] = set()
    for item in images.items:
        target = item["target"]
        assert isinstance(target, dict), "Publication image targets were validated."
        local_id = str(target["id"])
        frozen_target: Types.ProductJsonObject
        if target["kind"] == "character":
            source_id = images.character_ids_by_local_id[local_id]
            frozen_target = {
                "kind": "character",
                "product_character_id": str(character_slot_ids[source_id]),
            }
        else:
            frozen_target = {
                "kind": "lore_entry",
                "lorebook_snapshot_id": str(lorebook_snapshot_id),
                "lore_entry_id": str(images.lore_entry_ids_by_local_id[local_id]),
            }
        file_id = str(item["fileVersionId"])
        files.add(UUID(file_id))
        items.append(
            {
                "image_item_id": item["imageItemId"],
                "file_version_id": file_id,
                "target": frozen_target,
                "kind": item["kind"],
                "tags": item["tags"],
                "alt": item["alt"],
            }
        )
    starts: list[Types.ProductJsonObject] = [
        {
            "start_set_id": str(start_set_id),
            "content_blocks": images.start_blocks_by_entry_id[entry_id],
        }
        for entry_id, start_set_id in start_set_ids.items()
    ]
    for file_version_id in sorted(files):
        await retain_product_file_version(
            session,
            Types.ProductFileReferenceCommand(
                product_id=product_id,
                file_version_id=file_version_id,
                kind="snapshot",
                reference_id=snapshot_id,
            ),
        )
    return items, starts
