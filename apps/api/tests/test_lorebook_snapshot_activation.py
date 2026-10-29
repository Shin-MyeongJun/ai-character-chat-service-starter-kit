# 스냅샷 순서와 깊은 복사를 확인한다. priority 숫자가 커도 이 함수가 재정렬하지 않는 사례를 포함한다.
from copy import deepcopy
from uuid import uuid4

import pytest

from app.db.models.snapshot.lorebook import LorebookSnapshot
from app.modules.content.lorebook import types
from app.modules.content.lorebook.mapper import persistence
from app.modules.content.lorebook.service import query
from app.modules.content.lorebook.service.activation import validate_options


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


@pytest.mark.parametrize("version", [1, 1.0, True])
def test_activation_defaults_preserve_existing_version_equality(version):
    metadata = {"activation_options": {"version": version}, "unrelated": "retained"}
    before = deepcopy(metadata)
    options = validate_options(metadata)
    assert options is not None
    assert options["version"] is version
    assert (options["match"], options["scan_depth"], options["search_target"]) == (
        "any",
        9,
        "all",
    )
    options["exclusive_group"] = "changed"
    assert metadata == before
    assert validate_options({"unrelated": "retained"}) is None


@pytest.mark.parametrize(
    "option",
    [{"scan_depth": True}, {"partial_match": 1}, {"future_option": "unknown"}],
)
def test_activation_option_validation_keeps_boolean_and_unknown_key_rejection(option):
    with pytest.raises(ValueError):
        validate_options({"activation_options": {"version": 1, **option}})


def test_snapshot_mapper_to_activation_preserves_extensions_and_missing_optional_fields():
    item = entry(content="용", extension={"flags": [True, None]})
    snapshot = LorebookSnapshot(
        id=uuid4(),
        lorebook_id=None,
        version=1,
        snapshot_data={"entries": [item], "extension": {"labels": ["original"]}},
    )
    info = persistence.lorebook_snapshot_entity_to_info(snapshot)
    active, diagnostics = query.diagnose_entries(info.snapshot_data["entries"])
    assert active == [item]
    assert diagnostics == [
        {
            "id": item["id"],
            "included": True,
            "reason": "included",
            "order": 0,
            "estimated_tokens": 3,
            "placement": None,
        }
    ]
    active[0]["extension"]["flags"].append(False)
    info.snapshot_data["extension"]["labels"].append("info only")
    assert snapshot.snapshot_data["entries"][0]["extension"] == {"flags": [True, None]}
    assert snapshot.snapshot_data["extension"]["labels"] == ["original"]
    assert info.lorebook_id is None


def test_draft_diagnostics_still_reject_unknown_constructor_fields():
    command = types.DiagnoseDraftEntriesCommand(
        owner_id=uuid4(),
        entries=(entry(unexpected_field="invalid"),),
        messages=(),
    )
    with pytest.raises(TypeError, match="unexpected_field"):
        query.diagnose_draft_entries(command)
