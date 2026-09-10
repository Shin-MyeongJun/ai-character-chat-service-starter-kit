"""Compatibility exports; implementations live in role-specific service files."""

from app.modules.content.product.service.command.statistics import (
    enqueue_recent,
    process_pending,
    rebuild_day,
)
from app.modules.content.product.service.query.statistics import get_statistics

__all__ = ["enqueue_recent", "get_statistics", "process_pending", "rebuild_day"]
