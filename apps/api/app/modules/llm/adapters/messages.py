# chat_message_format=1이 있으면 역할과 본문만 허용하는 봉투로 검증한다.
# JSON이 아니거나 형식 표식이 없으면 None을 돌려 기존 문자열 입력 경로를 유지한다.
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
