"""Open JSON storage values, independent of domain validation and ORM models."""

from typing import TypeAlias

# These aliases describe decoded storage values; they neither validate nor coerce
# legacy documents. Domain-specific read views and validators remain separate.
JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]
