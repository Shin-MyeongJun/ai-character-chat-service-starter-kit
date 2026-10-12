"""Current content tags; parent locks serialize all connection mutations."""

from app.db.transaction import use_case_transaction
from app.modules.content.character import repository as Repository
from app.modules.content.character import types as Types
from app.modules.content.character.mapper import persistence as PersistenceMapper
from app.modules.content.character.mapper import tags as TagsPersistenceMapper
from app.modules.content.tag import types as TagTypes
from app.modules.content.tag.service import command as TagCommandService
from app.modules.content.tag.service import query as TagQueryService
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService


async def _get_tag_target(session, target_id, *, lock=False):
    row = await Repository.get_target_for_tag_access(session, target_id, lock=lock)
    info = PersistenceMapper.character_entity_to_info(row)
    if info is None:
        raise LookupError("Character not found.")
    return info


async def _get_public_tags(session, target_id) -> tuple[TagTypes.PublicTagInfo, ...]:
    links = TagsPersistenceMapper.public_tag_links_entities_to_info(
        await Repository.list_public_tag_links(session, target_id)
    )
    tags = await TagQueryService.get_tags(
        session, TagTypes.GetTagsCommand(tuple(link.tag_id for link in links))
    )
    return TagsPersistenceMapper.public_tag_links_infos_to_tags(links, tags)


async def _get_internal_tags(
    session, target_id
) -> tuple[TagTypes.InternalTagInfo, ...]:
    links = TagsPersistenceMapper.internal_tag_links_entities_to_info(
        await Repository.list_internal_tag_links(session, target_id)
    )
    tags = await TagQueryService.get_tags(
        session, TagTypes.GetTagsCommand(tuple(link.tag_id for link in links))
    )
    return TagsPersistenceMapper.internal_tag_links_infos_to_tags(links, tags)


async def list_public_tags(
    session, command: Types.PublicTagsCommand
) -> tuple[TagTypes.PublicTagInfo, ...]:
    info = await _get_tag_target(session, command.target_id)
    if info.owner_id != command.user_id:
        raise LookupError("Character not found.")
    return await _get_public_tags(session, command.target_id)


async def _write_public_tags(session, command, *, append):
    async with use_case_transaction(session):
        info = await _get_tag_target(session, command.target_id, lock=True)
        if info.owner_id != command.user_id:
            raise LookupError("Character not found.")
        links = TagsPersistenceMapper.public_tag_links_entities_to_info(
            await Repository.list_public_tag_links(session, command.target_id)
        )
        retained = tuple(link.tag_id for link in links)
        tags = await TagCommandService.resolve_tags(
            session, TagTypes.ResolveTagsCommand(command.names, retained)
        )
        requested = tuple(tag.id for tag in tags)
        ids = tuple(dict.fromkeys((*retained, *requested))) if append else requested
        await Repository.replace_public_tag_links(
            session, command.target_id, ids, command.user_id
        )
        return await _get_public_tags(session, command.target_id)


async def add_public_tags(
    session, command: Types.PublicTagsCommand
) -> tuple[TagTypes.PublicTagInfo, ...]:
    return await _write_public_tags(session, command, append=True)


async def replace_public_tags(
    session, command: Types.PublicTagsCommand
) -> tuple[TagTypes.PublicTagInfo, ...]:
    return await _write_public_tags(session, command, append=False)


async def remove_public_tag(session, command: Types.PublicTagsCommand) -> None:
    if command.tag_id is None:
        raise ValueError("Tag ID is required.")
    async with use_case_transaction(session):
        info = await _get_tag_target(session, command.target_id, lock=True)
        if info.owner_id != command.user_id:
            raise LookupError("Character not found.")
        await Repository.remove_public_tag_link(
            session, command.target_id, command.tag_id
        )


async def list_internal_tags(
    session, command: Types.InternalTagsCommand
) -> tuple[TagTypes.InternalTagInfo, ...]:
    await IdentityQueryService.require_admin(
        session, IdentityTypes.GetUserCommand(command.actor_id)
    )
    await _get_tag_target(session, command.target_id)
    return await _get_internal_tags(session, command.target_id)


async def _write_internal_tags(session, command, *, source, replace=False):
    async with use_case_transaction(session):
        actor = command.actor_id if source == "admin" else None
        if source == "admin":
            await IdentityQueryService.require_admin(
                session, IdentityTypes.GetUserCommand(actor)
            )
        await _get_tag_target(session, command.target_id, lock=True)
        links = TagsPersistenceMapper.internal_tag_links_entities_to_info(
            await Repository.list_internal_tag_links(session, command.target_id)
        )
        tags = await TagCommandService.resolve_tags(
            session,
            TagTypes.ResolveTagsCommand(
                command.names, tuple(link.tag_id for link in links)
            ),
        )
        if replace:
            requested = {tag.id for tag in tags}
            await Repository.remove_internal_tag_links(
                session,
                command.target_id,
                tuple(link.tag_id for link in links if link.tag_id not in requested),
            )
        protected = {link.tag_id for link in links if link.source == "admin"}
        for tag in tags:
            if source == "system" and tag.id in protected:
                continue
            await Repository.set_internal_tag_link(
                session, command.target_id, tag.id, source, actor
            )
        return await _get_internal_tags(session, command.target_id)


async def add_internal_tags(
    session, command: Types.InternalTagsCommand
) -> tuple[TagTypes.InternalTagInfo, ...]:
    return await _write_internal_tags(session, command, source="admin")


async def replace_internal_tags(
    session, command: Types.InternalTagsCommand
) -> tuple[TagTypes.InternalTagInfo, ...]:
    return await _write_internal_tags(session, command, source="admin", replace=True)


async def set_system_tags(
    session, command: Types.SystemTagsCommand
) -> tuple[TagTypes.InternalTagInfo, ...]:
    """Trusted application callers only; never exposed as an HTTP request."""
    return await _write_internal_tags(session, command, source="system")


async def _remove_internal_tag(session, command, *, source):
    if command.tag_id is None:
        raise ValueError("Tag ID is required.")
    async with use_case_transaction(session):
        if source == "admin":
            await IdentityQueryService.require_admin(
                session, IdentityTypes.GetUserCommand(command.actor_id)
            )
        await _get_tag_target(session, command.target_id, lock=True)
        links = TagsPersistenceMapper.internal_tag_links_entities_to_info(
            await Repository.list_internal_tag_links(session, command.target_id)
        )
        if source == "system" and any(
            link.tag_id == command.tag_id and link.source == "admin" for link in links
        ):
            raise ValueError("System cannot remove an administrator-assigned tag.")
        await Repository.remove_internal_tag_links(
            session, command.target_id, (command.tag_id,)
        )


async def remove_internal_tag(session, command: Types.InternalTagsCommand) -> None:
    await _remove_internal_tag(session, command, source="admin")


async def remove_system_tag(session, command: Types.SystemTagsCommand) -> None:
    await _remove_internal_tag(session, command, source="system")


async def list_system_tags(
    session, command: Types.SystemTagsCommand
) -> tuple[TagTypes.InternalTagInfo, ...]:
    """Trusted application use only; no corresponding HTTP endpoint."""
    await _get_tag_target(session, command.target_id)
    return await _get_internal_tags(session, command.target_id)
