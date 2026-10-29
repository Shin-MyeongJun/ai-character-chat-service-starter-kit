from collections.abc import Iterable
from typing import overload

from app.db.models.tag import Tag
from app.modules.content.tag import types as Types


@overload
def tag_entity_to_info(entity: Tag) -> Types.TagInfo: ...


@overload
def tag_entity_to_info(entity: None) -> None: ...


def tag_entity_to_info(entity: Tag | None) -> Types.TagInfo | None:
    if entity is None:
        return None
    return Types.TagInfo(
        id=entity.id,
        name=entity.name,
        description=entity.description,
        is_active=entity.is_active,
    )


def tags_entities_to_info(entities: Iterable[Tag]) -> tuple[Types.TagInfo, ...]:
    return tuple(tag_entity_to_info(entity) for entity in entities)
