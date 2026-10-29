# 서버 템플릿만 system 역할로 두고 설정·활성 로어·기억은 user 참조 JSON으로 넣는다.
# 원문은 position 순 역할 이력으로, 현재 사용자 입력은 ID 기준 한 번만 포함한다.
# estimated_tokens는 실제 tokenizer 값이 아니라 UTF-8 본문 바이트와 메시지별 여유분의 합이다.
import hashlib
import json
from functools import lru_cache
from importlib.resources import files
from typing import TypedDict
from uuid import UUID

from app.modules.chatting.prompt import types as Types
from app.modules.content.character import types as CharacterTypes
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as ProductTypes


class _CharacterReference(TypedDict):
    id: str
    data: dict[str, CharacterTypes.CharacterSnapshotJsonValue]


class _SceneReference(TypedDict):
    title: str | None
    content: str


class _ReferenceData(TypedDict):
    answer_character_id: str
    characters: list[_CharacterReference]
    settings: ProductTypes.ProductJsonObject
    scene: _SceneReference
    active_lore: list[LorebookTypes.LorebookSnapshotEntryData]
    memories: list[str]


def _has_positioned_lore(entry: LorebookTypes.LorebookSnapshotEntryData) -> bool:
    metadata = entry.get("metadata", {})
    # The renderer already required supplied metadata to be an object; None must
    # remain a failure rather than being silently converted to legacy metadata.
    assert metadata is not None, "Prompt lore metadata must be an object when supplied."
    return bool(metadata.get("activation_options"))


def validate_template(value: object) -> Types.TemplateInfo:
    if not isinstance(value, dict):
        raise Types.TemplateConfigurationError("Template must be an object.")
    if (
        value.get("template_id") != "character-answer"
        or type(value.get("version")) is not int
        or value["version"] != 1
    ):
        raise Types.TemplateConfigurationError("Unsupported template ID/version.")
    for key in ("role_rules", "expression_rules"):
        rules = value.get(key)
        if (
            not isinstance(rules, list)
            or not rules
            or any(not isinstance(rule, str) or not rule.strip() for rule in rules)
        ):
            raise Types.TemplateConfigurationError(f"Invalid template {key}.")
    digest = hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return Types.TemplateInfo(
        value["template_id"],
        value["version"],
        digest,
        tuple(value["role_rules"]),
        tuple(value["expression_rules"]),
    )


@lru_cache(maxsize=1)
def load_template() -> Types.TemplateInfo:
    """One server-owned resource, loaded at startup and cached until restart."""
    try:
        value = json.loads(
            files("app.modules.chatting.prompt.resources")
            .joinpath("default.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise Types.TemplateConfigurationError(
            "Cannot load default answer template."
        ) from exc
    return validate_template(value)


def build_prompt(command: Types.BuildPromptCommand) -> Types.PromptInfo:
    """Render v1 lore at its selected history boundary, preserving legacy envelopes.

    Lore remains user reference data at both positions. Only server template rules
    receive system authority; entry budgets have already been checked by selection.
    """
    runtime = command.runtime
    target = str(command.product_character_id)
    if target not in {item.id for item in runtime.characters}:
        raise ValueError("Answer character is absent from runtime.")
    if command.current_message.sender_type != "user":
        raise ValueError("Current input must be a user message.")
    start = runtime.start
    # Rendering already reads both scene fields unconditionally. A nullable view
    # may describe legacy absence, but no empty scene is synthesized for a prompt.
    assert start is not None, "Prompt rendering requires a start scene."
    references: _ReferenceData = {
        "answer_character_id": target,
        "characters": [{"id": c.id, "data": c.data} for c in runtime.characters],
        "settings": runtime.settings,
        "scene": {"title": start.title, "content": start.content},
        "active_lore": [
            entry
            for book in runtime.lorebooks
            if not book.targets or target in book.targets
            for entry in book.entries
        ],
        "memories": [item.content for item in command.memories],
    }
    positioned = [
        entry for entry in references["active_lore"] if _has_positioned_lore(entry)
    ]
    references["active_lore"] = [
        entry for entry in references["active_lore"] if not _has_positioned_lore(entry)
    ]
    messages = [
        {
            "role": "system",
            "content": "\n".join(
                (*command.template.role_rules, *command.template.expression_rules)
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"reference_data": references}, ensure_ascii=False),
        },
    ]
    if runtime.opening_message is not None:
        messages.append({"role": "assistant", "content": runtime.opening_message})
    before = [
        entry for entry in positioned if entry.get("placement") != "near_user_message"
    ]
    after = [
        entry for entry in positioned if entry.get("placement") == "near_user_message"
    ]
    if before:
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "reference_data": {
                            "active_lore": before,
                            "position": "before_history",
                        }
                    },
                    ensure_ascii=False,
                ),
            }
        )
    seen: set[UUID] = set()
    last_position = -1
    for item in command.recent_messages:
        if item.id in seen or item.position <= last_position:
            raise ValueError("History must contain unique IDs in position order.")
        seen.add(item.id)
        last_position = item.position
        if item.id == command.current_message.id:
            continue
        if item.position >= command.current_message.position:
            raise ValueError("History extends beyond current input.")
        if item.sender_type not in ("user", "character"):
            raise ValueError("Unsupported message role.")
        messages.append(
            {
                "role": "user" if item.sender_type == "user" else "assistant",
                "content": item.content,
            }
        )
    if after:
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "reference_data": {
                            "active_lore": after,
                            "position": "after_history",
                        }
                    },
                    ensure_ascii=False,
                ),
            }
        )
    messages.append({"role": "user", "content": command.current_message.content})
    request = json.dumps(
        {"chat_message_format": 1, "messages": messages}, ensure_ascii=False
    )
    # Conservative UTF-8 byte upper estimate plus per-message framing reserve.
    # No provider tokenizer exists in this project; this can reject valid prompts.
    tokens = sum(len(m["content"].encode()) + 32 for m in messages) + 32
    return Types.PromptInfo(request, tokens)
