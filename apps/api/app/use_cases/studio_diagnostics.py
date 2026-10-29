"""Unsaved studio diagnostics, using the same domain activation service as answers."""

from dataclasses import dataclass
from typing import Literal, TypedDict, cast
from uuid import UUID

from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service import query as LoreQuery
from app.use_cases.studio_content import lore_entry_value


@dataclass(frozen=True, slots=True)
class DiagnoseStudioLoreCommand:
    owner_id: UUID
    entries: tuple[dict[str, object], ...]
    messages: tuple[tuple[str, str], ...]
    manual_entry_ids: tuple[str, ...] = ()


class StudioLoreDiagnostics(TypedDict):
    items: list[LoreTypes.LorebookEntryDiagnostic]
    active_ids: list[str]
    ai_called: Literal[False]
    token_estimator: str


def diagnose_studio_lore(command: DiagnoseStudioLoreCommand) -> StudioLoreDiagnostics:
    """Validate transient editor values and return actual selection without AI or publication."""
    entries: list[LoreTypes.LorebookSnapshotEntryData] = []
    for row in command.entries:
        value = lore_entry_value(row)
        # lore_entry_value checked id and emitted every required snapshot field.
        # Preserve the same temporary dictionary and the domain's later validation.
        entry = cast(LoreTypes.LorebookSnapshotEntryData, value)
        entry["id"] = cast(str, row["id"])
        entries.append(entry)
    active, diagnostics = LoreQuery.diagnose_draft_entries(
        LoreTypes.DiagnoseDraftEntriesCommand(
            command.owner_id, tuple(entries), command.messages, command.manual_entry_ids
        )
    )
    return {
        "items": diagnostics,
        "active_ids": [str(entry["id"]) for entry in active],
        "ai_called": False,
        "token_estimator": "utf8-bytes-upper-bound-v1",
    }
