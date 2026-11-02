"""U15 matching contracts through snapshot, draft, live query and studio paths."""

from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.http import dependencies as HttpDependencies
from app.modules.content.lorebook import dependencies, repository, types
from app.modules.content.lorebook.router import router
from app.modules.content.lorebook.service import query
from app.modules.content.lorebook.service.util import matching
from app.use_cases.studio_content import lore_entry_value
from app.use_cases.studio_diagnostics import (
    DiagnoseStudioLoreCommand,
    diagnose_studio_lore,
)


def keyword_entry(
    mode: types.LorebookEntryMatchModeValue,
    triggers: list[str],
    options: dict[str, object] | None,
) -> types.LorebookSnapshotEntryData:
    metadata: dict[str, object] = {"labels": ["original"]}
    if options is not None:
        metadata["activation_options"] = {"version": 1, **options}
    return {
        "id": str(uuid4()),
        "content": "용",
        "entry_type": "world",
        "activation_type": "keyword",
        "is_enabled": True,
        "match_mode": mode,
        "key_triggers": triggers,
        "metadata": metadata,
    }


def assert_selection(
    entries: list[types.LorebookSnapshotEntryData],
    messages: tuple[tuple[str, str], ...],
    expected: list[types.LorebookSnapshotEntryData],
) -> list[types.LorebookEntryDiagnostic]:
    snapshot = types.LorebookSnapshotInfo(uuid4(), uuid4(), 1, {"entries": entries})
    before = deepcopy((entries, messages, snapshot))
    active = query.activate_snapshot_entries(
        types.ActivateSnapshotEntriesCommand(snapshot=snapshot, messages=messages)
    )
    draft_active, diagnostics = query.diagnose_draft_entries(
        types.DiagnoseDraftEntriesCommand(
            owner_id=uuid4(), entries=tuple(entries), messages=messages
        )
    )
    assert active.entries == draft_active == expected
    if len(messages) == 1:
        assert (
            query.activate_snapshot_entries(
                types.ActivateSnapshotEntriesCommand(
                    snapshot=snapshot, text=messages[0][1]
                )
            ).entries
            == expected
        )
    assert [item["id"] for item in diagnostics if item["included"]] == [
        item["id"] for item in expected
    ]
    assert (entries, messages, snapshot) == before
    for copied in (active.entries, draft_active):
        for item in copied:
            item["key_triggers"] = ["changed"]
            assert item.get("metadata") is not None
            metadata = item["metadata"]
            assert metadata is not None
            metadata["labels"] = ["changed"]
            options = metadata.get("activation_options")
            if isinstance(options, dict):
                options["case_sensitive"] = "changed"
    assert (entries, messages, snapshot) == before
    return diagnostics


@pytest.mark.parametrize("partial_match", [True, False])
@pytest.mark.parametrize(
    ("trigger", "text", "case_sensitive", "included"),
    [
        ("ABC", "ABC", True, True),
        ("ABC", "abc", True, False),
        ("ABC", "abc", False, True),
        ("ABC", "prefix ABC", False, False),
        ("ABC", "ABC suffix", True, False),
        ("ABC", "prefix ABC suffix", False, False),
        ("ABC", "xABC", True, False),
        ("ABC", "ABCx", False, False),
        ("ABC", " ABC ", False, False),
        ("ABC", "ABC\n", True, False),
        ("Straße", "STRASSE", False, True),
        ("Straße", "STRASSE", True, False),
    ],
)
def test_v1_exact_matches_the_entire_normalized_message(
    partial_match: bool, trigger: str, text: str, case_sensitive: bool, included: bool
) -> None:
    entry = keyword_entry(
        "exact",
        [trigger],
        {"case_sensitive": case_sensitive, "partial_match": partial_match},
    )
    assert_selection([entry], (("user", text),), [entry] if included else [])


@pytest.mark.parametrize("partial_match", [True, False])
@pytest.mark.parametrize(
    ("pattern", "text", "case_sensitive", "included"),
    [
        ("ABC", "ABC", True, True),
        ("ABC", "abc", True, False),
        ("abc", "ABC", True, False),
        ("abc", "abc", True, True),
        ("ABC", "abc", False, True),
        ("abc", "ABC", False, True),
        ("ABC", "prefix ABC suffix", True, True),
        ("ABC", "prefix abc suffix", True, False),
        ("ABC", "prefix abc suffix", False, True),
        ("^ABC$", "prefix ABC suffix", False, False),
        ("ÄBC", "äbc", False, True),
        ("ÄBC", "äbc", True, False),
    ],
)
def test_v1_regex_applies_case_option_without_changing_search_semantics(
    partial_match: bool, pattern: str, text: str, case_sensitive: bool, included: bool
) -> None:
    entry = keyword_entry(
        "regex",
        [pattern],
        {"case_sensitive": case_sensitive, "partial_match": partial_match},
    )
    assert_selection([entry], (("user", text),), [entry] if included else [])


@pytest.mark.parametrize("first_sensitive", [True, False])
def test_regex_cache_isolates_options_and_legacy_validation(
    first_sensitive: bool,
) -> None:
    pattern = f"^ABC-{uuid4().hex}$"
    text = pattern[1:-1].lower()
    for case_sensitive in (first_sensitive, not first_sensitive, first_sensitive):
        entry = keyword_entry("regex", [pattern], {"case_sensitive": case_sensitive})
        assert_selection([entry], (("user", text),), [] if case_sensitive else [entry])
        matching.validate_regex(pattern)
        legacy = keyword_entry("regex", [pattern], None)
        snapshot = types.LorebookSnapshotInfo(uuid4(), None, 1, {"entries": [legacy]})
        assert query.activate_snapshot_entries(
            types.ActivateSnapshotEntriesCommand(snapshot=snapshot, text=text)
        ).entries == [legacy]


@pytest.mark.parametrize("mode", ["exact", "regex"])
def test_v1_omitted_case_option_defaults_to_case_insensitive(
    mode: types.LorebookEntryMatchModeValue,
) -> None:
    entry = keyword_entry(mode, ["ABC"], {})
    assert_selection([entry], (("user", "abc"),), [entry])


@pytest.mark.parametrize(
    ("mode", "trigger", "text", "included"),
    [
        ("exact", "ABC", "abc", True),
        ("exact", "ABC", "prefix ABC suffix", False),
        ("contains", "ABC", "prefix abc suffix", True),
        ("regex", "ABC", "prefix abc suffix", True),
        ("regex", "^ABC$", "prefix abc suffix", False),
    ],
)
def test_legacy_snapshot_without_options_keeps_text_order_and_case_policy(
    mode: types.LorebookEntryMatchModeValue, trigger: str, text: str, included: bool
) -> None:
    entry = keyword_entry(mode, [trigger], None)
    entry["token_budget"] = 0
    snapshot = types.LorebookSnapshotInfo(uuid4(), None, 1, {"entries": [entry]})
    before = deepcopy(snapshot)
    result = query.activate_snapshot_entries(
        types.ActivateSnapshotEntriesCommand(
            snapshot=snapshot, text=text, messages=(("user", "unrelated"),)
        )
    )
    assert result.entries == ([entry] if included else [])
    assert snapshot == before


@pytest.mark.parametrize("case_sensitive", [True, False])
@pytest.mark.parametrize("pattern", ["[", r"(?<=A)BC", r"(A)\1"])
def test_invalid_and_backtracking_only_regex_keep_domain_error_and_http_translation(
    case_sensitive: bool, pattern: str
) -> None:
    entry = keyword_entry("regex", [pattern], {"case_sensitive": case_sensitive})
    snapshot = types.LorebookSnapshotInfo(uuid4(), None, 1, {"entries": [entry]})
    before = deepcopy(snapshot)
    with pytest.raises(matching.InvalidLorebookRegex) as stored_error:
        query.activate_snapshot_entries(
            types.ActivateSnapshotEntriesCommand(snapshot=snapshot, text="ABC")
        )
    assert str(stored_error.value) == "Invalid lorebook entry regular expression."
    with pytest.raises(HTTPException) as http_error, HttpDependencies.errors():
        query.diagnose_draft_entries(
            types.DiagnoseDraftEntriesCommand(
                owner_id=uuid4(), entries=(entry,), messages=(("user", "ABC"),)
            )
        )
    assert http_error.value.status_code == 422
    assert http_error.value.detail == str(stored_error.value)
    assert snapshot == before


def test_legacy_invalid_regex_keeps_stored_error_translation() -> None:
    entry = keyword_entry("regex", ["["], None)
    snapshot = types.LorebookSnapshotInfo(uuid4(), None, 1, {"entries": [entry]})
    with pytest.raises(ValueError) as error:
        query.activate_snapshot_entries(
            types.ActivateSnapshotEntriesCommand(snapshot=snapshot, text="ABC")
        )
    assert (
        str(error.value) == "Stored lorebook entry has an invalid regular expression."
    )
    assert isinstance(error.value.__cause__, matching.InvalidLorebookRegex)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_sensitive", [True, False])
async def test_authored_invalid_v1_regex_keeps_lorebook_http_422(
    case_sensitive: bool,
) -> None:
    app = FastAPI()
    app.include_router(router)
    async with AsyncSession() as session:

        async def get_session() -> AsyncSession:
            return session

        app.dependency_overrides[dependencies.get_lorebook_session] = get_session
        app.dependency_overrides[dependencies.get_current_owner_id] = uuid4
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            response = await client.post(
                "/lorebooks/entries",
                json={
                    "lorebook_id": str(uuid4()),
                    "content": "Lore",
                    "activation_type": "keyword",
                    "match_mode": "regex",
                    "key_triggers": ["["],
                    "metadata": {
                        "activation_options": {
                            "version": 1,
                            "case_sensitive": case_sensitive,
                        }
                    },
                },
            )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid lorebook input."}
        assert not session.in_transaction()


@pytest.mark.parametrize("mode", ["exact", "regex"])
@pytest.mark.parametrize(("match", "included"), [("any", True), ("all", False)])
def test_v1_keyword_combinations_keep_history_depth_and_speaker_filter(
    mode: types.LorebookEntryMatchModeValue, match: str, included: bool
) -> None:
    entry = keyword_entry(
        mode,
        ["ABC", "XYZ"],
        {
            "match": match,
            "scan_depth": 2,
            "search_target": "user",
            "case_sensitive": True,
        },
    )
    messages = (("user", "XYZ"), ("character", "XYZ"), ("user", "ABC"))
    assert_selection([entry], messages, [entry] if included else [])
    assert entry["metadata"] is not None
    entry["metadata"]["activation_options"] = {
        "version": 1,
        "match": "all",
        "scan_depth": 3,
        "search_target": "user",
        "case_sensitive": True,
    }
    assert_selection([entry], messages, [entry])


def test_v1_matching_preserves_ranking_budget_group_and_diagnostic_contracts() -> None:
    entries = [
        keyword_entry("exact", ["ABC"], {"exclusive_group": "group", "order": 7})
        for _ in range(4)
    ]
    oversized, later_id, winner, later_order = entries
    for entry, value in zip(entries, (1, 3, 2, 4), strict=True):
        entry["id"] = str(UUID(int=value))
        entry["priority"] = 20
    oversized["priority"] = 100
    oversized["token_budget"] = 2  # Three UTF-8 bytes for one Korean character.
    winner["token_budget"] = 3
    assert later_order["metadata"] is not None
    later_order["metadata"]["activation_options"] = {
        "version": 1,
        "exclusive_group": "group",
        "order": 8,
    }
    diagnostics = assert_selection(entries, (("user", "ABC"),), [winner])
    assert [item["id"] for item in diagnostics] == [
        item["id"] for item in (oversized, winner, later_id, later_order)
    ]
    assert [item["reason"] for item in diagnostics] == [
        "entry_budget_exceeded",
        "included",
        "exclusive_group",
        "exclusive_group",
    ]
    assert [item["order"] for item in diagnostics] == [None, 0, None, None]
    assert all(item["estimated_tokens"] == 3 for item in diagnostics)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["exact", "regex"])
async def test_live_query_retains_legacy_even_when_entry_has_v1_options(
    monkeypatch: pytest.MonkeyPatch, mode: types.LorebookEntryMatchModeValue
) -> None:
    from app.db.models.lorebook import LorebookEntry

    entry = LorebookEntry(
        id=uuid4(),
        lorebook_id=uuid4(),
        content="original",
        entry_type="world",
        activation_type="keyword",
        match_mode=mode,
        key_triggers=["ABC"],
        priority=0,
        token_budget=0,
        placement="before_history",
        is_enabled=True,
        metadata_={"activation_options": {"version": 1, "case_sensitive": True}},
    )
    before = deepcopy(entry.metadata_)
    monkeypatch.setattr(
        repository,
        "list_enabled_entries_by_activation_type",
        AsyncMock(return_value=[entry]),
    )
    async with AsyncSession() as session:
        active = await query.activate_keyword_entries(
            session,
            types.ActivateKeywordEntriesCommand(
                lorebook_ids=[entry.lorebook_id], text="abc"
            ),
        )
    assert [item.entry_id for item in active] == [entry.id]
    assert entry.metadata_ == before


@pytest.mark.parametrize(("case_sensitive", "included"), [(True, False), (False, True)])
def test_actual_studio_contains_translation_agrees_with_published_snapshot(
    case_sensitive: bool, included: bool
) -> None:
    row: dict[str, object] = {
        "id": "studio-entry",
        "title": "Lore",
        "content": "용",
        "activation": "keyword",
        "keywords": ["ABC"],
        "caseSensitive": case_sensitive,
        "partialMatch": False,
    }
    before = deepcopy(row)
    messages = (("user", "prefix abc suffix"),)
    result = diagnose_studio_lore(
        DiagnoseStudioLoreCommand(
            owner_id=uuid4(),
            entries=(row,),
            messages=messages,
        )
    )
    fields = lore_entry_value(row)
    assert fields["match_mode"] == "contains"
    entry = keyword_entry("contains", ["ABC"], None)
    entry["id"] = "studio-entry"
    entry["metadata"] = fields["metadata"]
    assert_selection([entry], messages, [entry] if included else [])
    assert result["active_ids"] == (["studio-entry"] if included else [])
    assert result["ai_called"] is False
    assert result["items"][0]["reason"] == (
        "included" if included else "keyword_mismatch"
    )
    assert row == before
