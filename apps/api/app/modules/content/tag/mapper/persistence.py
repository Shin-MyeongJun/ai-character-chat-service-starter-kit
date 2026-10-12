from app.modules.content.tag import types as Types


def tag_entity_to_info(entity) -> Types.TagInfo | None:
    if entity is None:
        return None
    return Types.TagInfo(entity.id, entity.name, entity.description, entity.is_active)


def tags_entities_to_info(entities) -> tuple[Types.TagInfo, ...]:
    return tuple(tag_entity_to_info(entity) for entity in entities)
