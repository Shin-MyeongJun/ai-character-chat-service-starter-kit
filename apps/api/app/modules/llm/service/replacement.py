"""Compatibility exports; implementations live in role-specific service files."""

from app.modules.llm.service.command.replacement import (
    announce_retirement,
    resolve_execution,
)
from app.modules.llm.service.views.replacement import execution_notice

__all__ = ["announce_retirement", "execution_notice", "resolve_execution"]
