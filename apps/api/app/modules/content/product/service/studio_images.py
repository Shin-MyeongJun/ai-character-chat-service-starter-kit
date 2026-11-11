"""Validate and normalize U19 chat images at the Studio document boundary."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from app.modules.content.product import types as Types

_PARAGRAPH_SEPARATOR = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")


@dataclass(frozen=True, slots=True)
class StudioImagePublicationDraftInfo:
    items: tuple[Types.ProductJsonObject, ...]
    file_version_ids: tuple[UUID, ...]
    start_blocks_by_scene_id: dict[str, list[Types.ProductJsonValue]]
    digest: str


def _read_uuid(value: object, field: str) -> UUID:
    if not isinstance(value, str):
        raise ValueError(f"Invalid studio {field}: expected UUID.")
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid studio {field}: expected UUID.") from exc


def _read_objects(
    value: Types.ProductJsonValue, field: str
) -> list[Types.ProductJsonObject]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid studio {field}: expected list.")
    rows: list[Types.ProductJsonObject] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError(f"Invalid studio {field}: expected object.")
        rows.append(row)
    return rows


def _read_tags(value: Types.ProductJsonValue) -> list[Types.ProductJsonValue]:
    if not isinstance(value, list):
        raise ValueError("Studio image tags must be a list.")
    tags: dict[str, None] = {}
    for tag in value:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError("Studio image tags must be nonblank strings.")
        tags[tag.strip()] = None
    return list(tags)


def normalize_studio_chat_images(
    document: Types.ProductJsonObject,
) -> Types.ProductJsonObject:
    """Preserve legacy missing fields and canonicalize only authored image data."""
    result = {
        key: value
        for key, value in document.items()
        if key != Types.RETIRED_STUDIO_IMAGE_ITEMS
    }
    targets = {
        kind: {
            row_id
            for row in _read_objects(document.get(field, []), field)
            if isinstance(row_id := row.get("id"), str)
        }
        for kind, field in (("character", "characters"), ("lore_entry", "lorebooks"))
    }
    ids: set[UUID] = set()
    if "chatImageItems" in document:
        items: list[Types.ProductJsonValue] = []
        for item in _read_objects(document["chatImageItems"], "chatImageItems"):
            item_id = _read_uuid(item.get("imageItemId"), "imageItemId")
            if item_id in ids:
                raise ValueError("Studio image item IDs must be distinct.")
            ids.add(item_id)
            target = item.get("target")
            if not isinstance(target, dict):
                raise ValueError("Studio image target is required.")
            target_kind, target_id = target.get("kind"), target.get("id")
            if (
                not isinstance(target_kind, str)
                or target_kind not in targets
                or not isinstance(target_id, str)
                or target_id not in targets[target_kind]
            ):
                raise ValueError("Studio image target is missing.")
            kind = item.get("kind")
            if (
                not isinstance(kind, str)
                or kind not in ("expression", "situation")
                or (target_kind == "lore_entry" and kind != "situation")
            ):
                raise ValueError("Invalid studio image kind for target.")
            alt = item.get("alt")
            if not isinstance(alt, str):
                raise ValueError("Studio image alt must be text.")
            file_id = item.get("fileVersionId")
            items.append(
                {
                    "imageItemId": str(item_id),
                    "fileVersionId": str(_read_uuid(file_id, "fileVersionId"))
                    if file_id is not None
                    else None,
                    "target": {"kind": target_kind, "id": target_id},
                    "kind": kind,
                    "tags": _read_tags(item.get("tags")),
                    "alt": alt,
                }
            )
        result["chatImageItems"] = items

    if "scenes" in document:
        scenes: list[Types.ProductJsonValue] = []
        for scene in _read_objects(document["scenes"], "scenes"):
            if "openingImagePlacements" not in scene:
                scenes.append(scene)
                continue
            opening = scene.get("opening", "")
            assert isinstance(opening, str), "Studio opening shape has been validated."
            paragraph_count = sum(
                bool(part.strip()) for part in _PARAGRAPH_SEPARATOR.split(opening)
            )
            placements: list[Types.ProductJsonValue] = []
            for placement in _read_objects(
                scene["openingImagePlacements"], "openingImagePlacements"
            ):
                item_id = _read_uuid(placement.get("imageItemId"), "imageItemId")
                after = placement.get("afterParagraph")
                if item_id not in ids:
                    raise ValueError("Studio opening image item is missing.")
                if type(after) is not int or not 0 <= after <= paragraph_count:
                    raise ValueError(
                        "Studio opening image paragraph position is out of range."
                    )
                placements.append(
                    {"imageItemId": str(item_id), "afterParagraph": after}
                )
            scenes.append({**scene, "openingImagePlacements": placements})
        result["scenes"] = scenes
    return result


def get_studio_image_ids(document: Types.ProductJsonObject, field: str) -> set[UUID]:
    """Read item or non-null file IDs from a validated draft."""
    return {
        _read_uuid(row[field], field)
        for row in _read_objects(document.get("chatImageItems", []), "chatImageItems")
        if row.get(field) is not None
    }


def get_retired_studio_image_ids(
    document: Mapping[str, Types.ProductJsonValue],
) -> set[UUID]:
    value = document.get(Types.RETIRED_STUDIO_IMAGE_ITEMS, [])
    assert isinstance(value, list), "Retired studio image IDs are server-managed."
    return {_read_uuid(item, Types.RETIRED_STUDIO_IMAGE_ITEMS) for item in value}


def _opening_paragraphs(opening: str) -> list[str]:
    paragraphs: list[str] = []
    offset = 0
    prefix = ""
    for separator in _PARAGRAPH_SEPARATOR.finditer(opening):
        part = opening[offset : separator.end()]
        if opening[offset : separator.start()].strip():
            paragraphs.append(prefix + part)
            prefix = ""
        else:
            prefix += part
        offset = separator.end()
    tail = prefix + opening[offset:]
    if tail.strip():
        paragraphs.append(tail)
    elif paragraphs:
        paragraphs[-1] += tail
    return paragraphs


def prepare_studio_image_publication(
    document: Types.ProductJsonObject,
) -> StudioImagePublicationDraftInfo | None:
    scenes = document.get("scenes", [])
    if "chatImageItems" not in document and not (
        isinstance(scenes, list)
        and any(
            isinstance(scene, dict) and "openingImagePlacements" in scene
            for scene in scenes
        )
    ):
        return None
    validated = normalize_studio_chat_images(document)
    items = _read_objects(validated.get("chatImageItems", []), "chatImageItems")
    if not items:
        return None
    files: set[UUID] = set()
    blocks_by_item_id: dict[str, Types.ProductJsonObject] = {}
    for item in items:
        item_id = str(item["imageItemId"])
        file_id = item["fileVersionId"]
        if file_id is None:
            raise ValueError("Studio chat images must be uploaded before publication.")
        files.add(_read_uuid(file_id, "fileVersionId"))
        blocks_by_item_id[item_id] = {
            "type": "image",
            "image_item_id": item_id,
            "file_version_id": file_id,
            "alt": item["alt"],
        }

    starts: dict[str, list[Types.ProductJsonValue]] = {}
    for scene in _read_objects(validated.get("scenes", []), "scenes"):
        opening = scene.get("opening", "")
        scene_id = scene.get("id")
        if not isinstance(opening, str) or not isinstance(scene_id, str):
            raise ValueError("Invalid studio opening scene.")
        placements: dict[int, list[Types.ProductJsonObject]] = {}
        for placement in _read_objects(
            scene.get("openingImagePlacements", []), "openingImagePlacements"
        ):
            position = placement["afterParagraph"]
            assert isinstance(position, int), "Placement was normalized above."
            placements.setdefault(position, []).append(
                blocks_by_item_id[str(placement["imageItemId"])]
            )
        blocks: list[Types.ProductJsonValue] = [*placements.get(0, ())]
        for position, paragraph in enumerate(_opening_paragraphs(opening), 1):
            blocks.append({"type": "text", "text": paragraph})
            blocks.extend(placements.get(position, ()))
        starts[scene_id] = blocks
    digest = hashlib.sha256(
        json.dumps(
            {"items": items, "starts": starts}, sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    return StudioImagePublicationDraftInfo(
        tuple(items), tuple(sorted(files)), starts, digest
    )
