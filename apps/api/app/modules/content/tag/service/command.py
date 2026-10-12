from app.db.transaction import use_case_transaction
from app.modules.content.tag import repository as Repository
from app.modules.content.tag import types as Types
from app.modules.content.tag.mapper import persistence as PersistenceMapper
from app.modules.identity import types as IdentityTypes
from app.modules.identity.service import query as IdentityQueryService
from sqlalchemy.exc import IntegrityError


def _prepare_tag_names(names: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(names, (tuple, list)) or any(
        not isinstance(name, str) or not name.strip() for name in names
    ):
        raise ValueError("Tag names must be nonblank strings.")
    return tuple(dict.fromkeys(name.strip() for name in names))


async def resolve_tags(
    session, command: Types.ResolveTagsCommand
) -> tuple[Types.TagInfo, ...]:
    """Trusted content caller supplies only retained IDs read under its parent lock."""
    names = _prepare_tag_names(command.names)
    async with use_case_transaction(session):
        resolved = {}
        # All writers resolve shared names in the same order to avoid deadlocks.
        for name in sorted(names):
            info = PersistenceMapper.tag_entity_to_info(
                await Repository.resolve_tag(session, name)
            )
            if info is None:
                raise ValueError("Tag name changed concurrently; retry the request.")
            if not info.is_active and info.id not in command.retained_ids:
                raise ValueError("Inactive tags cannot be newly assigned.")
            resolved[name] = info
        return tuple(resolved[name] for name in names)


async def create_tag(session, command: Types.CreateTagCommand) -> Types.TagInfo:
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        names = _prepare_tag_names((command.name,))
        info = PersistenceMapper.tag_entity_to_info(
            await Repository.resolve_tag(session, names[0], command.description)
        )
        if info is None:
            raise ValueError("Tag name changed concurrently; retry the request.")
        # Existing names retain their metadata; editing uses update_tag.
        return info


async def update_tag(session, command: Types.UpdateTagCommand) -> Types.TagInfo:
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        info = PersistenceMapper.tag_entity_to_info(
            await Repository.get_tag(session, command.tag_id, exclusive=True)
        )
        if info is None:
            raise LookupError("Tag not found.")
        name = _prepare_tag_names((command.name,))[0]
        try:
            return PersistenceMapper.tag_entity_to_info(
                await Repository.update_tag(session, info.id, name, command.description)
            )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) == "23505":
                raise ValueError("Tag name already exists.") from exc
            raise


async def deactivate_tag(session, command: Types.DeactivateTagCommand) -> Types.TagInfo:
    async with use_case_transaction(session):
        await IdentityQueryService.require_admin(
            session, IdentityTypes.GetUserCommand(command.actor_id)
        )
        info = PersistenceMapper.tag_entity_to_info(
            await Repository.get_tag(session, command.tag_id, exclusive=True)
        )
        if info is None:
            raise LookupError("Tag not found.")
        return PersistenceMapper.tag_entity_to_info(
            await Repository.deactivate_tag(session, info.id)
        )
