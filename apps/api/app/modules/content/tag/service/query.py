from app.modules.content.tag import repository as Repository
from app.modules.content.tag import types as Types
from app.modules.content.tag.mapper import persistence as PersistenceMapper
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def get_admin_tag(session, command: Types.AdminGetTagCommand) -> Types.TagInfo:
    await IdentityQueryService.require_admin(
        session, IdentityTypes.GetUserCommand(command.actor_id)
    )
    info = await get_tag(session, Types.GetTagCommand(command.tag_id))
    if info is None:
        raise LookupError("Tag not found.")
    return info


async def get_tag(session, command: Types.GetTagCommand) -> Types.TagInfo | None:
    return PersistenceMapper.tag_entity_to_info(
        await Repository.get_tag(session, command.tag_id)
    )


async def get_tag_by_name(
    session, command: Types.GetTagByNameCommand
) -> Types.TagInfo | None:
    return PersistenceMapper.tag_entity_to_info(
        await Repository.get_tag_by_name(session, command.name.strip())
    )


async def get_tags(session, command: Types.GetTagsCommand) -> tuple[Types.TagInfo, ...]:
    return PersistenceMapper.tags_entities_to_info(
        await Repository.get_tags(session, command.tag_ids)
    )
