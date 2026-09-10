from app.modules.identity import repository as Repository
from app.modules.identity import types as Types
from app.modules.identity.mapper import persistence as PersistenceMapper


async def require_admin(session, command: Types.GetUserCommand) -> Types.UserAccessInfo:
    row = await Repository.get_user(session, command.user_id)
    info = PersistenceMapper.user_entity_to_access_info(row)
    if info is None or info.role != "admin" or info.status != "active":
        raise LookupError("Administrative operation unavailable.")
    return info
