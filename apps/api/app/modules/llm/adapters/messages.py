"""Decode the optional neutral chat envelope; preserve legacy string requests."""

import json


def decode_messages(request_json: str) -> list[dict[str, str]] | None:
    try:
        value = json.loads(request_json)
    except ValueError:
        return None
    if not isinstance(value, dict) or "chat_message_format" not in value:
        return None
    if (
        type(value["chat_message_format"]) is not int
        or value["chat_message_format"] != 1
    ):
        raise ValueError("Unsupported chat message format.")
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Chat messages must be a nonempty list.")
    for message in messages:
        if (
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message["role"] not in ("system", "user", "assistant")
            or not isinstance(message["content"], str)
            or not message["content"].strip()
        ):
            raise ValueError("Invalid neutral chat message.")
    return messages
