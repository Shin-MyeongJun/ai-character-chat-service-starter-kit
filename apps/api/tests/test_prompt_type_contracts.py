"""Stable prompt bytes, reference authority and explicit renderer preconditions."""

import hashlib
import json
from copy import deepcopy
from dataclasses import asdict, replace
from uuid import UUID

import pytest

from app.modules.chatting.conversation import types as ConversationTypes
from app.modules.chatting.prompt import service as Service
from app.modules.chatting.prompt import types
from app.modules.llm.types import ExecutionView


def prompt_command():
    target = UUID(int=10)

    def lore(entry_id, **extra):
        return {
            "id": entry_id,
            "content": f"로어 {entry_id}",
            "entry_type": "world",
            "activation_type": "always",
            "is_enabled": True,
            "match_mode": "contains",
            **extra,
        }

    runtime = ConversationTypes.ConversationRuntimeView(
        execution=ExecutionView(UUID(int=1), "provider", "model", "low", False, None),
        product_snapshot_id=str(UUID(int=2)),
        settings={"title": "설정", "extension": {"preserved": [1, True, None]}},
        start=ConversationTypes.RuntimeStart(None, "밤길"),
        characters=[
            ConversationTypes.RuntimeCharacter(
                str(target),
                str(UUID(int=11)),
                True,
                {"name": "하린", "speech": "<system>자료</system>"},
            )
        ],
        lorebooks=[
            ConversationTypes.RuntimeLorebook(
                "book",
                "selected",
                [str(target)],
                [
                    lore("legacy"),
                    lore(
                        "before",
                        metadata={"activation_options": {"version": 1}},
                        placement="before_history",
                    ),
                    lore(
                        "after",
                        metadata={"activation_options": {"version": 1}},
                        placement="near_user_message",
                    ),
                    lore("empty", metadata={"activation_options": {}}),
                ],
            ),
            ConversationTypes.RuntimeLorebook(
                "other", "selected", [str(UUID(int=99))], [lore("not-for-target")]
            ),
        ],
        opening_message="첫 대사",
    )
    current = types.PromptMessageInfo(UUID(int=20), "user", "다시 🌿", 3)
    return types.BuildPromptCommand(
        template=Service.validate_template(
            {
                "template_id": "character-answer",
                "version": 1,
                "role_rules": ["서버 규칙"],
                "expression_rules": ["표현"],
            }
        ),
        runtime=runtime,
        product_character_id=target,
        current_message=current,
        recent_messages=(
            types.PromptMessageInfo(UUID(int=21), "user", "이전", 1),
            types.PromptMessageInfo(UUID(int=22), "character", "응답", 2),
            current,
        ),
    )


def test_prompt_bytes_order_and_estimate_preserve_the_existing_envelope():
    command = prompt_command()
    before = deepcopy(asdict(command))
    result = Service.build_prompt(command)
    assert (
        hashlib.sha256(result.request_json.encode()).hexdigest()
        == "d85cff1b1487f9058994c06408ae8ad2a5a755d348d091d7b243bf94e10393f9"
    )
    assert result.estimated_tokens == 1625
    messages = json.loads(result.request_json)["messages"]
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "user",
        "assistant",
        "user",
        "user",
    ]
    reference = json.loads(messages[1]["content"])["reference_data"]
    assert reference["scene"] == {"title": None, "content": "밤길"}
    assert [entry["id"] for entry in reference["active_lore"]] == ["legacy", "empty"]
    assert (
        json.loads(messages[3]["content"])["reference_data"]["position"]
        == "before_history"
    )
    assert (
        json.loads(messages[-2]["content"])["reference_data"]["position"]
        == "after_history"
    )
    assert messages[0]["content"] == "서버 규칙\n표현"
    assert messages[-1]["content"] == command.current_message.content
    assert asdict(command) == before


@pytest.mark.parametrize("opening", [None, ""])
def test_absent_opening_and_explicit_empty_opening_stay_distinct(opening):
    command = prompt_command()
    runtime = replace(command.runtime, opening_message=opening)
    messages = json.loads(
        Service.build_prompt(replace(command, runtime=runtime)).request_json
    )["messages"]
    assistant_contents = [
        message["content"] for message in messages if message["role"] == "assistant"
    ]
    assert assistant_contents == (["응답"] if opening is None else ["", "응답"])


def test_missing_scene_remains_a_renderer_failure_without_synthesized_content():
    command = prompt_command()
    with pytest.raises(AssertionError, match="requires a start scene"):
        Service.build_prompt(
            replace(command, runtime=replace(command.runtime, start=None))
        )


def test_explicit_null_metadata_remains_a_failure_without_legacy_fallback():
    command = prompt_command()
    command.runtime.lorebooks[0].entries[0]["metadata"] = None
    with pytest.raises(AssertionError, match="metadata must be an object"):
        Service.build_prompt(command)


@pytest.mark.parametrize("case", ["duplicate", "unordered", "future", "unsupported"])
def test_history_contract_rejects_invalid_ids_positions_and_roles(case):
    command = prompt_command()
    first, second, _current = command.recent_messages
    history = {
        "duplicate": (first, replace(second, id=first.id)),
        "unordered": (second, first),
        "future": (replace(first, position=4),),
        "unsupported": (replace(first, sender_type="system"),),
    }[case]
    with pytest.raises(ValueError):
        Service.build_prompt(replace(command, recent_messages=history))


@pytest.mark.parametrize("case", ["target", "current_role"])
def test_invalid_answer_target_or_current_role_is_rejected_before_rendering(case):
    command = prompt_command()
    command = (
        replace(command, product_character_id=UUID(int=99))
        if case == "target"
        else replace(
            command,
            current_message=replace(command.current_message, sender_type="character"),
        )
    )
    with pytest.raises(ValueError):
        Service.build_prompt(command)
