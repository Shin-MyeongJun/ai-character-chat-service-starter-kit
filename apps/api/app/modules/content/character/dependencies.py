"""Compatibility imports for existing dependency overrides."""

from app.http.character_dependencies import (
    get_character_session,
    get_current_owner_id,
    require_character_admin,
    require_character_moderator,
)

__all__ = [
    "get_character_session",
    "get_current_owner_id",
    "require_character_admin",
    "require_character_moderator",
]
