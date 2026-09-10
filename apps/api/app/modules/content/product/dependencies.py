"""Compatibility exports for existing application dependency overrides."""

from app.http.dependencies import (
    get_current_owner_id,
    get_product_session,
    require_product_admin,
)

__all__ = ["get_current_owner_id", "get_product_session", "require_product_admin"]
