"""Studio document values shared by release construction and unsaved diagnostics."""

from app.modules.content.lorebook.service.activation import validate_options


def lore_entry_value(lore: dict) -> dict:
    """Translate editor fields into validated v1 snapshot options with legacy defaults."""
    if any(not isinstance(lore.get(key), str) for key in ("id", "title", "content")) or not lore["id"]:
        raise ValueError("Lore ID, title and content must be strings.")
    if not isinstance(lore.get("keywords", []), list) or any(not isinstance(value, str) for value in lore.get("keywords", [])) or type(lore.get("enabled", True)) is not bool:
        raise ValueError("Invalid lore triggers/enabled value.")
    if lore.get("tokenBudget") is not None and (type(lore["tokenBudget"]) is not int or not 1 <= lore["tokenBudget"] <= 32000):
        raise ValueError("Invalid lore entry budget.")
    options = {"version": 1, "match": lore.get("match", "any"), "scan_depth": lore.get("scanDepth", 9), "search_target": lore.get("searchTarget", "all"), "partial_match": lore.get("partialMatch", True), "case_sensitive": lore.get("caseSensitive", False), "order": lore.get("order", 100), "exclusive_group": lore.get("exclusiveGroup", "")}
    metadata = {"activation_options": options}
    validate_options(metadata)
    return {"title": lore["title"], "content": lore["content"], "entry_type": {"장소": "location", "세계관": "world", "인물": "character_relation", "사건": "event"}.get(lore.get("category"), "world"), "activation_type": lore.get("activation", "always"), "key_triggers": lore.get("keywords") or None, "match_mode": "contains", "priority": {"필수": 100, "높음": 75, "보통": 50, "낮음": 25}.get(lore.get("priority"), 50), "token_budget": lore.get("tokenBudget"), "placement": "before_history" if lore.get("placement", "before") == "before" else "near_user_message", "is_enabled": lore.get("enabled", True), "metadata": metadata}


def scene_entry_value(scene: dict) -> dict:
    """Keep first dialogue separate from context; store textual language/time/view cues.

    characterId/placeId remain editor references. They do not imply per-scene
    participant or location relations, which the current runtime does not model.
    """
    language, perspective = scene.get("language", "한국어"), scene.get("perspective", "2인칭")
    if language not in ("한국어", "English", "日本語") or perspective not in ("1인칭", "2인칭", "3인칭"):
        raise ValueError("Invalid scene language or perspective.")
    for key in ("storyTime", "variants"):
        if not isinstance(scene.get(key, ""), str):
            raise ValueError("Invalid scene text option.")  # noqa: TRY004 - public validation maps to HTTP 422
    content = "\n\n".join(part for part in (scene.get("background"), scene.get("initialNotes"), f"응답 언어: {language}\n서술 시점: {perspective}", f"이야기 시간: {scene['storyTime']}" if scene.get("storyTime") else "", f"장면 변형 지침: {scene['variants']}" if scene.get("variants") else "") if part)
    return {"title": scene["title"], "content": content, "entry_type": "start_set", "activation_type": "always", "metadata": {"studio_scene_v1": {"opening": scene["opening"], "language": language, "story_time": scene.get("storyTime", ""), "perspective": perspective, "variants": scene.get("variants", "")}}}
