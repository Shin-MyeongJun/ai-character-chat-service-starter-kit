"""Freeze studio image references within the product publication transaction."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as Types
from app.modules.content.product.mapper import persistence as PersistenceMapper
from app.modules.content.product.service import views as ViewsService
from app.modules.content.product.service.command.file_versions import (
    retain_product_file_version,
)


@dataclass(frozen=True, slots=True)
class _PublicationImages:
    items: list[Types.ProductJsonObject]
    starts: list[Types.ProductJsonObject]
    digest: str


def _freeze_studio_publication_images(
    images: Types.StudioPublicationImagesInfo,
    character_slot_ids: Mapping[UUID, UUID],
    start_set_ids: Mapping[UUID, UUID],
    lorebook_snapshot_id: UUID,
) -> _PublicationImages:
    items: list[Types.ProductJsonObject] = []
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
    return _PublicationImages(items, starts, images.digest)


async def _inherit_publication_images(
    session: AsyncSession,
    previous: Types.ProductSnapshotInfo,
    character_slot_ids: Mapping[UUID, UUID],
    lorebooks: Mapping[UUID, LorebookTypes.LorebookSnapshotInfo],
    start_set_ids: Mapping[UUID, UUID],
    data: Types.ProductSnapshotData,
) -> _PublicationImages:
    runtime = await ViewsService.get_snapshot_runtime(
        session, Types.ProductSnapshotCommand(previous.id)
    )
    # Old slots point to immutable component snapshots. Only a common source
    # identity can link those slots to their counterparts in this publication.
    character_slots: dict[str, UUID] = {}
    for slot in runtime.composition.characters:
        source_id = runtime.characters[slot.character_snapshot_id].character_id
        if source_id is not None and source_id in character_slot_ids:
            character_slots[str(slot.id)] = character_slot_ids[source_id]
    lore_targets: dict[tuple[str, str], str] = {}
    for old in runtime.lorebooks.values():
        if old.lorebook_id is not None and old.lorebook_id in lorebooks:
            current = lorebooks[old.lorebook_id]
            for entry in current.snapshot_data["entries"]:
                if entry["entry_type"] != "start_set":
                    lore_targets[str(old.id), entry["id"]] = str(current.id)
    items: list[Types.ProductJsonObject] = []
    for item in previous.snapshot_data["chat_image_items"]:
        target = item["target"]
        if not isinstance(target, dict):
            raise ValueError("Invalid published chat image target.")
        if target["kind"] == "character":
            slot_id = character_slots.get(str(target["product_character_id"]))
            if slot_id is None:
                raise ValueError(
                    "Published image character is missing. Update images in Studio."
                )
            new_target: Types.ProductJsonObject = {
                "kind": "character",
                "product_character_id": str(slot_id),
            }
        elif target["kind"] == "lore_entry":
            entry_id = str(target["lore_entry_id"])
            book_id = lore_targets.get((str(target["lorebook_snapshot_id"]), entry_id))
            if book_id is None:
                raise ValueError(
                    "Published image lore entry is missing. Update images in Studio."
                )
            new_target = {
                "kind": "lore_entry",
                "lorebook_snapshot_id": book_id,
                "lore_entry_id": entry_id,
            }
        else:
            raise ValueError("Invalid published chat image target.")
        items.append({**item, "target": new_target})

    starts = _rebind_published_starts(
        previous.snapshot_data, runtime.composition.starts, start_set_ids, data
    )
    return _PublicationImages(
        items, starts, previous.snapshot_data["chat_image_digest"]
    )


def _rebind_published_starts(
    previous: Types.ProductSnapshotData,
    previous_starts: Sequence[Types.SnapshotStartInfo],
    start_set_ids: Mapping[UUID, UUID],
    data: Types.ProductSnapshotData,
) -> list[Types.ProductJsonObject]:
    source_starts = {str(start.id): start.source_entry_id for start in previous_starts}
    files_by_item = {
        str(item["image_item_id"]): str(item["file_version_id"])
        for item in previous["chat_image_items"]
    }
    scene_options = data.get("studio_start_options", {})
    starts: list[Types.ProductJsonObject] = []
    for start in previous["starts"]:
        entry = source_starts.get(str(start["start_set_id"]))
        if entry is None or entry not in start_set_ids:
            raise ValueError(
                "Published image start option is missing. Update placements in Studio."
            )
        options = scene_options.get(str(entry), {})
        opening = (
            options.get("opening", data.get("opening_message"))
            if isinstance(options, dict)
            else None
        )
        blocks = start["content_blocks"]
        if not isinstance(blocks, list):
            raise ValueError("Invalid published start blocks.")
        text = []
        for block in blocks:
            parsed = PersistenceMapper.content_block_json_to_info(block)
            if isinstance(parsed, Types.TextContentBlockInfo):
                text.append(parsed.text)
            elif files_by_item.get(str(parsed.image_item_id)) != str(
                parsed.file_version_id
            ):
                raise ValueError("Published opening image does not match the catalog.")
        if opening != "".join(text):
            raise ValueError(
                "Published opening text changed. Update image placements in Studio."
            )
        starts.append(
            {"start_set_id": str(start_set_ids[entry]), "content_blocks": blocks}
        )
    return starts


async def _retain_publication_files(
    session: AsyncSession,
    product_id: UUID,
    snapshot_id: UUID,
    images: _PublicationImages,
) -> None:
    for file_version_id in sorted(
        {UUID(str(item["file_version_id"])) for item in images.items}
    ):
        await retain_product_file_version(
            session,
            Types.ProductFileReferenceCommand(
                product_id=product_id,
                file_version_id=file_version_id,
                kind="snapshot",
                reference_id=snapshot_id,
            ),
        )
