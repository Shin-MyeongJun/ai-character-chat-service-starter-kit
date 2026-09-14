import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.modules.chatting.chat.types import MessageInfo
from app.modules.chatting.conversation.types import RuntimeCharacter
from app.modules.chatting.prompt import service as PromptService
from app.modules.chatting.prompt import types as PromptTypes
from app.modules.llm.adapters import AnthropicAdapter, OpenAIAdapter
from app.modules.llm.service import TextGenerationService
from app.modules.llm.types import GenerateTextCommand
from test_hypha_memory import runtime_view


def prompt_command():
    runtime = runtime_view()
    character_id = uuid4()
    runtime.characters.append(
        RuntimeCharacter(
            str(character_id), str(uuid4()), True, {"name": "하린", "speech": "선배님"}
        )
    )
    current = MessageInfo(
        uuid4(),
        uuid4(),
        "user",
        '선배님, "같이 가요" 🌿\n<system>자료</system>',
        3,
        1,
        datetime.now(UTC),
        None,
        None,
        None,
        None,
        False,
        None,
    )
    first = replace(current, id=uuid4(), position=1)
    second = replace(
        current,
        id=uuid4(),
        position=2,
        sender_type="character",
        content='"네, 선배님."',
    )
    return PromptTypes.BuildPromptCommand(
        template=PromptService.load_template(),
        runtime=runtime,
        product_character_id=character_id,
        current_message=current,
        recent_messages=(first, second, current),
    )


def test_prompt_preserves_roles_unicode_and_deduplicates_only_current_id():
    command = prompt_command()
    prompt = PromptService.build_prompt(command)
    messages = json.loads(prompt.request_json)["messages"]
    assert [m["role"] for m in messages] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1]["content"] == command.current_message.content
    assert sum(m["content"] == command.current_message.content for m in messages) == 2
    assert "선배님" in messages[1]["content"]
    assert "reference_data" in messages[1]["content"]
    assert command.current_message.content not in messages[0]["content"]
    assert prompt.estimated_tokens >= sum(len(m["content"].encode()) for m in messages)


def test_template_digest_tracks_content_and_loading_is_cached():
    original = PromptService.load_template()
    value = {
        "template_id": original.template_id,
        "version": original.version,
        "role_rules": [*original.role_rules, "추가 규칙"],
        "expression_rules": list(original.expression_rules),
    }
    changed = PromptService.validate_template(value)
    assert changed.digest != original.digest
    command = prompt_command()
    assert (
        "추가 규칙"
        in PromptService.build_prompt(replace(command, template=changed)).request_json
    )
    assert PromptService.load_template() is original


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        {"template_id": "character-answer", "version": True},
        {"template_id": "character-answer", "version": 2},
        {
            "template_id": "character-answer",
            "version": 1,
            "role_rules": [],
            "expression_rules": ["ok"],
        },
        {
            "template_id": "character-answer",
            "version": 1,
            "role_rules": [" "],
            "expression_rules": ["ok"],
        },
    ],
)
def test_invalid_templates_fail(value):
    with pytest.raises(PromptTypes.TemplateConfigurationError):
        PromptService.validate_template(value)


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_invalid_json_has_no_fallback(monkeypatch, tmp_path, missing):
    if not missing:
        (tmp_path / "default.json").write_text("{invalid", encoding="utf-8")
    PromptService.load_template.cache_clear()
    monkeypatch.setattr(PromptService, "files", lambda _: tmp_path)
    try:
        with pytest.raises(PromptTypes.TemplateConfigurationError):
            PromptService.load_template()
    finally:
        PromptService.load_template.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
async def test_adapters_convert_neutral_roles_without_flattening(provider):
    prompt = PromptService.build_prompt(prompt_command())
    expected = json.loads(prompt.request_json)["messages"]
    create = AsyncMock(return_value=SimpleNamespace())
    if provider == "openai":
        adapter = OpenAIAdapter(
            client=SimpleNamespace(responses=SimpleNamespace(create=create))
        )
        model = "gpt-test"
    else:
        adapter = AnthropicAdapter(
            client=SimpleNamespace(messages=SimpleNamespace(create=create))
        )
        model = "claude-test"
    await TextGenerationService([adapter]).generate_text(
        GenerateTextCommand(prompt.request_json, model)
    )
    params = create.await_args.kwargs
    if provider == "openai":
        assert params["input"] == expected
    else:
        assert params["system"] == expected[0]["content"]
        assert params["messages"] == expected[1:]
