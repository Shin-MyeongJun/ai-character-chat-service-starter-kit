"""Validate and normalize U19 chat images at the Studio document boundary."""

import re
from collections.abc import Mapping
from uuid import UUID

from app.modules.content.product import types as Types

_PARAGRAPH_SEPARATOR = re.compile(r"\r?\n(?:[ \t]*\r?\n)+")


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
