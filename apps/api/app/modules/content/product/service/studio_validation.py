"""Validate editor structure without requiring a complete publishable work."""

from collections.abc import Mapping
from uuid import UUID


def _strings(value: Mapping[str, object], names: tuple[str, ...]) -> None:
    for name in names:
        if name in value and not isinstance(value[name], str):
            raise ValueError(f"Invalid studio {name}: expected text.")


def _tags(value: Mapping[str, object]) -> None:
    if "tags" in value:
        names = value["tags"]
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name.strip() for name in names
        ):
            raise ValueError("Studio tags must be a list of nonblank names.")


def _rows(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"Invalid studio {label}: expected a list.")
    rows: list[dict[str, object]] = []
    ids: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            raise ValueError(f"Invalid studio {label} component.")
        identity = row.get("id")
        if not isinstance(identity, str) or not identity.strip() or identity in ids:
            raise ValueError(f"Studio {label} IDs must be distinct nonblank strings.")
        ids.add(identity)
        rows.append(row)
    return rows


def _assets(character: Mapping[str, object]) -> None:
    for asset in _rows(character.get("assets", []), "character assets"):
        _strings(asset, ("name", "usage", "mediaId"))
        if "usage" in asset and asset["usage"] not in (
            "portrait",
            "expression",
            "scene",
        ):
            raise ValueError("Invalid studio image usage.")
        if "mediaId" in asset:
            media_id = asset["mediaId"]
            if not isinstance(media_id, str):
                raise ValueError("Invalid studio image mediaId.")
            try:
                UUID(media_id)
            except ValueError as exc:
                raise ValueError("Invalid studio image mediaId.") from exc


def validate_studio_document_shape(document: Mapping[str, object]) -> None:
    """Keep missing/blank authored text and unuploaded assets usable as drafts.

    Known fields have fixed types; nonempty local references must resolve in this
    document. Extension keys are retained and input objects are never modified.
    Domain lengths/options and publication readiness have their own validators.
    """
    work = document.get("work", {})
    if not isinstance(work, dict):
        raise ValueError("Studio work profile is required.")
    _strings(
        work, ("title", "introduction", "visibility", "worldRules", "defaultSceneId")
    )
    _tags(work)
    characters = _rows(document.get("characters", []), "characters")
    lores = _rows(document.get("lorebooks", []), "lorebooks")
    scenes = _rows(document.get("scenes", []), "scenes")
    for character in characters:
        _strings(
            character,
            ("name", "persona", "introduction", "dialogue", "relationships", "role"),
        )
        _tags(character)
        _assets(character)
    for lore in lores:
        _strings(
            lore,
            (
                "title",
                "content",
                "activation",
                "category",
                "priority",
                "placement",
                "match",
                "searchTarget",
                "exclusiveGroup",
            ),
        )
        _tags(lore)
        if "activation" in lore and lore["activation"] not in (
            "always",
            "keyword",
            "semantic",
            "manual",
        ):
            raise ValueError("Invalid studio lore activation.")
        if "keywords" in lore:
            keywords = lore["keywords"]
            if not isinstance(keywords, list) or any(
                not isinstance(word, str) for word in keywords
            ):
                raise ValueError("Invalid studio lore keywords.")
        for name in ("enabled", "partialMatch", "caseSensitive"):
            if name in lore and type(lore[name]) is not bool:
                raise ValueError(f"Invalid studio lore {name}.")
        for name in ("scanDepth", "order", "tokenBudget"):
            if (
                name in lore
                and not (name == "tokenBudget" and lore[name] is None)
                and type(lore[name]) is not int
            ):
                raise ValueError(f"Invalid studio lore {name}.")
    character_ids = {row["id"] for row in characters}
    scene_ids = {row["id"] for row in scenes}
    default_scene = work.get("defaultSceneId", "")
    if default_scene and default_scene not in scene_ids:
        raise ValueError("Default start scene is missing.")
    for scene in scenes:
        _strings(
            scene,
            (
                "title",
                "opening",
                "characterId",
                "background",
                "initialNotes",
                "language",
                "perspective",
                "storyTime",
                "variants",
            ),
        )
        character_id = scene.get("characterId", "")
        if character_id and character_id not in character_ids:
            raise ValueError("Scene character is missing.")
