from app.modules.identity import types as Types


def user_entity_to_access_info(entity) -> Types.UserAccessInfo | None:
    if entity is None:
        return None
    return Types.UserAccessInfo(entity.id, entity.role, entity.status)
