"""Versioned lore selection shared by snapshot runtime and draft diagnostics."""

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import cast

from app.modules.content.lorebook import types as Types
from app.modules.content.lorebook.service.util import matching as MatchingServiceUtil


def validate_options(
    metadata: Mapping[str, object] | None,
) -> Types.LorebookActivationOptions | None:
    """Validate opt-in v1 options; absent metadata preserves legacy snapshot behavior."""
    options = (metadata or {}).get("activation_options")
    if options is None:
        return None
    if not isinstance(options, dict) or options.get("version") != 1:
        raise ValueError("Unsupported lore activation options version.")
    allowed = {
        "version",
        "match",
        "scan_depth",
        "search_target",
        "partial_match",
        "case_sensitive",
        "order",
        "exclusive_group",
    }
    if set(options) - allowed:
        raise ValueError("Unknown lore activation option.")
    defaults = {
        "version": 1,
        "match": "any",
        "scan_depth": 9,
        "search_target": "all",
        "partial_match": True,
        "case_sensitive": False,
        "order": 100,
        "exclusive_group": "",
    }
    result = {**defaults, **options}
    if result["match"] not in ("any", "all") or result["search_target"] not in (
        "all",
        "user",
    ):
        raise ValueError("Invalid lore match/search target.")
    for name, low, high in (("scan_depth", 1, 100), ("order", 0, 100000)):
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError(f"Invalid lore {name}.")
    if (
        any(
            type(result[name]) is not bool
            for name in ("partial_match", "case_sensitive")
        )
        or not isinstance(result["exclusive_group"], str)
        or len(result["exclusive_group"]) > 200
    ):
        raise ValueError("Invalid lore boolean/group option.")
    # Every option key/value above is validated after filling defaults. Preserve
    # the existing version equality rule, including numeric 1.0 and True.
    return cast(Types.LorebookActivationOptions, result)


def _matches(
    text: str, trigger: str, mode: str, options: Types.LorebookActivationOptions | None
) -> bool:
    """Use Unicode word boundaries for v1 whole-word matching and retain legacy modes."""
    if not options:
        if mode == "regex":
            try:
                return MatchingServiceUtil.regex_matches(trigger, text)
            except MatchingServiceUtil.InvalidLorebookRegex as exc:
                raise ValueError(
                    "Stored lorebook entry has an invalid regular expression."
                ) from exc
        if mode == "exact":
            return text.casefold() == trigger.casefold()
        if mode == "contains":
            return trigger.casefold() in text.casefold()
        raise ValueError("Stored lorebook entry has an invalid match mode.")
    if mode == "regex":
        # v1 studio uses contains; legacy regex uses its existing safety validator.
        return MatchingServiceUtil.regex_matches(trigger, text)
    if not options["case_sensitive"]:
        text, trigger = text.casefold(), trigger.casefold()
    if options["partial_match"]:
        return trigger in text
    return re.search(r"(?<!\w)" + re.escape(trigger) + r"(?!\w)", text) is not None


def diagnose_entries(
    entries: list[Types.LorebookSnapshotEntryData],
    *,
    text: str = "",
    messages: Sequence[tuple[str, str]] = (),
    manual_entry_ids: Sequence[str] = (),
) -> tuple[list[Types.LorebookSnapshotEntryData], list[Types.LorebookEntryDiagnostic]]:
    """Select immutable entries and explain exclusions using the actual runtime rules.

    Priority desc/order asc wins exclusive groups. V1 entry budgets use the same
    conservative UTF-8-byte upper estimate as prompt construction; oversize entries
    are excluded whole rather than silently truncating authored instructions.
    """
    known = {
        str(entry["id"]) for entry in entries if entry["entry_type"] != "start_set"
    }
    if set(map(str, manual_entry_ids)) - known:
        raise ValueError("Manual lore ID is outside the authorized snapshot.")
    prepared = [(entry, validate_options(entry.get("metadata"))) for entry in entries]
    # Legacy snapshots retain their stored ordering when no v1 option is present.
    if any(options for _, options in prepared):
        prepared.sort(
            key=lambda pair: (
                -pair[0].get("priority", 0),
                pair[1]["order"] if pair[1] else 100,
                str(pair[0]["id"]),
            )
        )
    groups: set[str] = set()
    active: list[Types.LorebookSnapshotEntryData] = []
    diagnostics: list[Types.LorebookEntryDiagnostic] = []
    for entry, options in prepared:
        reason: Types.LorebookActivationReason = "included"
        if not entry["is_enabled"]:
            reason = "disabled"
        elif entry["entry_type"] == "start_set":
            reason = "start_scene"
        elif entry["activation_type"] == "manual":
            if str(entry["id"]) not in set(map(str, manual_entry_ids)):
                reason = "manual_not_selected"
        elif entry["activation_type"] == "semantic":
            reason = "semantic_not_supported"
        elif entry["activation_type"] == "keyword":
            history = (
                list(messages)
                if options and messages
                else ([("user", text)] if text else [])
            )
            if options:
                # Depth counts the last N messages before filtering by speaker.
                history = history[-options["scan_depth"] :]
                history = [
                    (role, value)
                    for role, value in history
                    if options["search_target"] == "all" or role == "user"
                ]
            hits = [
                any(
                    value and _matches(value, trigger, entry["match_mode"], options)
                    for _, value in history
                )
                for trigger in entry.get("key_triggers") or []
            ]
            if not hits or not (
                all(hits) if options and options["match"] == "all" else any(hits)
            ):
                reason = "keyword_mismatch"
        elif entry["activation_type"] != "always":
            raise ValueError("Stored lorebook entry has an invalid activation type.")
        if reason == "included" and options:
            token_budget = entry.get("token_budget")
            if (
                token_budget is not None
                and len(entry["content"].encode("utf-8")) > token_budget
            ):
                reason = "entry_budget_exceeded"
        group = options["exclusive_group"].strip() if options else ""
        if reason == "included" and group:
            if group in groups:
                reason = "exclusive_group"
            else:
                groups.add(group)
        included = reason == "included"
        if included:
            active.append(deepcopy(entry))
        diagnostics.append(
            {
                "id": str(entry["id"]),
                "included": included,
                "reason": reason,
                "order": len(active) - 1 if included else None,
                "estimated_tokens": len(entry["content"].encode("utf-8")),
                "placement": entry.get("placement"),
            }
        )
    return active, diagnostics
