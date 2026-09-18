# 스냅샷 순서와 깊은 복사를 확인한다. priority 숫자가 커도 이 함수가 재정렬하지 않는 사례를 포함한다.
from copy import deepcopy
from uuid import uuid4

import pytest
from app.modules.content.lorebook import types
from app.modules.content.lorebook.service import query


def entry(activation_type="always", **overrides):
    return {
        "id": str(uuid4()),
        "content": "Published lore",
        "entry_type": "world",
        "activation_type": activation_type,
        "is_enabled": True,
        "key_triggers": ["dragon"],
        "match_mode": "contains",
        "metadata": {"tags": ["published"]},
        **overrides,
    }


def activate(entries, text=""):
    snapshot = types.LorebookSnapshotInfo(uuid4(), uuid4(), 1, {"entries": entries})
    return query.activate_snapshot_entries(
        types.ActivateSnapshotEntriesCommand(snapshot=snapshot, text=text)
    )


def test_snapshot_activation_filters_types_preserves_order_and_copies_values():
    first = entry("keyword", priority=1)
    second = entry(priority=100)
    entries = [
        first,
        entry("semantic"),
        entry("manual"),
        entry("keyword", key_triggers=["castle"]),
        entry(entry_type="start_set"),
        entry(is_enabled=False),
        entry("keyword", entry_type="start_set"),
        entry("keyword", is_enabled=False),
        second,
    ]
    before = deepcopy(entries)
    result = activate(entries, "The DRAGON wakes")
    assert result.entries == [first, second]
    result.entries[0]["metadata"]["tags"].append("changed")
    assert entries == before


@pytest.mark.parametrize(
    ("mode", "trigger", "text", "matches"),
    [
        ("exact", "Dragon", "dragon", True),
        ("exact", "Dragon", "the dragon", False),
        ("contains", "Dragon", "The DRAGON wakes", True),
        ("contains", "Dragon", "A wyvern wakes", False),
        ("regex", r"\bdragons?\b", "Two DRAGONS wake", True),
        ("regex", "^dragon$", "dragon wakes", False),
    ],
)
def test_snapshot_keyword_modes(mode, trigger, text, matches):
    item = entry("keyword", match_mode=mode, key_triggers=[trigger])
    assert activate([item], text).entries == ([item] if matches else [])


def test_empty_text_only_activates_always_even_when_regex_matches_empty():
    always = entry()
    assert activate(
        [entry("keyword", match_mode="regex", key_triggers=[".*"]), always]
    ).entries == [always]


@pytest.mark.parametrize("triggers", [None, [], ["castle", "dragon"]])
def test_keyword_requires_at_least_one_matching_trigger(triggers):
    item = entry("keyword", key_triggers=triggers)
    assert activate([item], "dragon").entries == ([item] if triggers else [])


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"match_mode": "regex", "key_triggers": ["["]}, "invalid regular expression"),
        ({"match_mode": "unknown"}, "invalid match mode"),
        ({"activation_type": "unknown"}, "invalid activation type"),
    ],
)
def test_invalid_snapshot_activation_fails_explicitly(overrides, error):
    item = entry("keyword")
    item.update(overrides)
    with pytest.raises(ValueError, match=error):
        activate([item], "dragon")
