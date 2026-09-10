"""Compatibility imports for existing dependency overrides."""

from app.http.lorebook_dependencies import (
    get_current_owner_id,
    get_lorebook_session,
    require_lorebook_admin,
    require_lorebook_moderator,
)

__all__ = [
    "get_current_owner_id",
    "get_lorebook_session",
    "require_lorebook_admin",
    "require_lorebook_moderator",
]
