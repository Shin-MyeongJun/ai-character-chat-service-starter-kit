"""Studio document values shared by release construction and unsaved diagnostics."""

from collections.abc import Mapping
from typing import TypedDict, cast

from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service.activation import validate_options


class StudioAsset(TypedDict, total=False):
    id: str
    mediaId: str
    usage: str


class StudioCharacter(TypedDict, total=False):
    id: str
    name: str
    persona: str
    introduction: str
    dialogue: str
    relationships: str
    role: str
    tags: list[str]
    assets: list[StudioAsset]


class StudioWork(TypedDict, total=False):
    title: str
    introduction: str
    worldRules: str
    visibility: str
    defaultSceneId: str
    tags: list[str]


class StudioScene(TypedDict, total=False):
    id: str
    title: str
    opening: str
    characterId: str
    background: str
    initialNotes: str
    language: str
    perspective: str
    storyTime: str
    variants: str


class StudioLore(TypedDict, total=False):
    id: str
    title: str
    content: str
    tags: list[str]
    category: object
    priority: object
    activation: LoreTypes.LorebookEntryActivationTypeValue
    keywords: list[str]
    enabled: bool
    tokenBudget: int | None


class StudioDocument(TypedDict, total=False):
    work: StudioWork
    characters: list[StudioCharacter]
    lorebooks: list[StudioLore]
    scenes: list[StudioScene]


def lore_entry_value(
    lore: Mapping[str, object],
) -> LoreTypes.LorebookEntryCommandFields:
    """Translate editor fields into validated v1 snapshot options with legacy defaults."""
    if (
        any(not isinstance(lore.get(key), str) for key in ("id", "title", "content"))
        or not lore["id"]
    ):
        raise ValueError("Lore ID, title and content must be strings.")
    keywords = lore.get("keywords", [])
    if (
        not isinstance(keywords, list)
        or any(not isinstance(value, str) for value in keywords)
        or type(lore.get("enabled", True)) is not bool
    ):
        raise ValueError("Invalid lore triggers/enabled value.")
    if lore.get("tokenBudget") is not None and (
        type(lore["tokenBudget"]) is not int or not 1 <= lore["tokenBudget"] <= 32000
    ):
        raise ValueError("Invalid lore entry budget.")
    options = {
        "version": 1,
        "match": lore.get("match", "any"),
        "scan_depth": lore.get("scanDepth", 9),
        "search_target": lore.get("searchTarget", "all"),
        "partial_match": lore.get("partialMatch", True),
        "case_sensitive": lore.get("caseSensitive", False),
        "order": lore.get("order", 100),
        "exclusive_group": lore.get("exclusiveGroup", ""),
    }
    metadata: dict[str, object] = {"activation_options": options}
    validate_options(metadata)
    # The checks above own text/triggers/budget; activation remains a passthrough
    # editor field validated by the public lore command/diagnostic boundary.
    fields = cast(StudioLore, lore)
    entry_types: dict[object, LoreTypes.LorebookEntryTypeValue] = {
        "장소": "location",
        "세계관": "world",
        "인물": "character_relation",
        "사건": "event",
    }
    priorities: dict[object, int] = {"필수": 100, "높음": 75, "보통": 50, "낮음": 25}
    return {
        "title": fields["title"],
        "content": fields["content"],
        "entry_type": entry_types.get(lore.get("category"), "world"),
        "activation_type": fields.get("activation", "always"),
        "key_triggers": fields.get("keywords") or None,
        "match_mode": "contains",
        "priority": priorities.get(lore.get("priority"), 50),
        "token_budget": fields.get("tokenBudget"),
        "placement": "before_history"
        if lore.get("placement", "before") == "before"
        else "near_user_message",
        "is_enabled": fields.get("enabled", True),
        "metadata": metadata,
    }


def scene_entry_value(
    scene: Mapping[str, object],
) -> LoreTypes.LorebookEntryCommandFields:
    """Keep first dialogue separate from context; store textual language/time/view cues.

    characterId/placeId remain editor references. They do not imply per-scene
    participant or location relations, which the current runtime does not model.
    """
    language, perspective = (
        scene.get("language", "한국어"),
        scene.get("perspective", "2인칭"),
    )
    if language not in ("한국어", "English", "日本語") or perspective not in (
        "1인칭",
        "2인칭",
        "3인칭",
    ):
        raise ValueError("Invalid scene language or perspective.")
    for key in ("storyTime", "variants"):
        if not isinstance(scene.get(key, ""), str):
            raise ValueError("Invalid scene text option.")  # noqa: TRY004 - public validation maps to HTTP 422
    # Publication checks title/opening/background/notes before calling this helper.
    # Keep the original missing-key and malformed-input behavior for direct calls.
    fields = cast(StudioScene, scene)
    content = "\n\n".join(
        part
        for part in (
            fields.get("background"),
            fields.get("initialNotes"),
            f"응답 언어: {language}\n서술 시점: {perspective}",
            f"이야기 시간: {fields['storyTime']}" if fields.get("storyTime") else "",
            f"장면 변형 지침: {fields['variants']}" if fields.get("variants") else "",
        )
        if part
    )
    return {
        "title": fields["title"],
        "content": content,
        "entry_type": "start_set",
        "activation_type": "always",
        "metadata": {
            "studio_scene_v1": {
                "opening": fields["opening"],
                "language": language,
                "story_time": fields.get("storyTime", ""),
                "perspective": perspective,
                "variants": fields.get("variants", ""),
            }
        },
    }
