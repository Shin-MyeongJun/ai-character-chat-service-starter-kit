from app.modules.content.character import types as Types


def media_entity_to_info(entity) -> Types.CharacterMediaInfo | None:
    if entity is None:
        return None
    return Types.CharacterMediaInfo(
        **{
            name: getattr(entity, name)
            for name in Types.CharacterMediaInfo.__dataclass_fields__
        }
    )
