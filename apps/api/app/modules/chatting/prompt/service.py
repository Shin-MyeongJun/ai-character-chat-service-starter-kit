import hashlib
import json
from functools import lru_cache
from importlib.resources import files

from app.modules.chatting.prompt import types as Types


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
    runtime = command.runtime
    target = str(command.product_character_id)
    if target not in {item.id for item in runtime.characters}:
        raise ValueError("Answer character is absent from runtime.")
    if command.current_message.sender_type != "user":
        raise ValueError("Current input must be a user message.")
    references = {
        "answer_character_id": target,
        "characters": [{"id": c.id, "data": c.data} for c in runtime.characters],
        "settings": runtime.settings,
        "scene": {"title": runtime.start.title, "content": runtime.start.content},
        "active_lore": [
            entry
            for book in runtime.lorebooks
            if not book.targets or target in book.targets
            for entry in book.entries
        ],
        "memories": [item.content for item in command.memories],
    }
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
    seen = set()
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
    messages.append({"role": "user", "content": command.current_message.content})
    request = json.dumps(
        {"chat_message_format": 1, "messages": messages}, ensure_ascii=False
    )
    # Conservative UTF-8 byte upper estimate plus per-message framing reserve.
    # No provider tokenizer exists in this project; this can reject valid prompts.
    tokens = sum(len(m["content"].encode()) + 32 for m in messages) + 32
    return Types.PromptInfo(request, tokens)
