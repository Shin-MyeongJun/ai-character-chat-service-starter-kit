"""Unsaved studio diagnostics, using the same domain activation service as answers."""

from dataclasses import dataclass
from uuid import UUID

from app.modules.content.lorebook import types as LoreTypes
from app.modules.content.lorebook.service import query as LoreQuery
from app.use_cases.studio_content import lore_entry_value


@dataclass(frozen=True, slots=True)
class DiagnoseStudioLoreCommand:
    owner_id: UUID
    entries: tuple[dict, ...]
    messages: tuple[tuple[str, str], ...]
    manual_entry_ids: tuple[str, ...] = ()


def diagnose_studio_lore(command: DiagnoseStudioLoreCommand) -> dict:
    """Validate transient editor values and return actual selection without AI or publication."""
    entries = []
    for row in command.entries:
        value = lore_entry_value(row)
        value["id"] = row["id"]
        entries.append(value)
    active, diagnostics = LoreQuery.diagnose_draft_entries(LoreTypes.DiagnoseDraftEntriesCommand(command.owner_id, tuple(entries), command.messages, command.manual_entry_ids))
    return {"items": diagnostics, "active_ids": [str(entry["id"]) for entry in active], "ai_called": False, "token_estimator": "utf8-bytes-upper-bound-v1"}
