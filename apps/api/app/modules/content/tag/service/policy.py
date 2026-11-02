"""Pure link policies; callers own authorization, parent locks and persistence."""

from uuid import UUID

from app.modules.content.tag import types as Types


def select_public_tag_ids(command: Types.SelectPublicTagIdsCommand) -> tuple[UUID, ...]:
    """Append after retained links, or use the requested replacement order."""
    if command.append:
        return tuple(dict.fromkeys((*command.retained_ids, *command.requested_ids)))
    return command.requested_ids


def plan_internal_tag_changes(
    command: Types.PlanInternalTagChangesCommand,
) -> Types.InternalTagChangesInfo:
    """Keep admin assignments when system tags are set; admin may take over."""
    requested_ids = set(command.requested_ids)
    remove_ids = (
        tuple(
            link.tag_id
            for link in command.links
            if link.tag_id not in requested_ids
            and (command.source != "system" or link.source != "admin")
        )
        if command.replace
        else ()
    )
    protected_ids = {link.tag_id for link in command.links if link.source == "admin"}
    set_ids = tuple(
        tag_id
        for tag_id in command.requested_ids
        if command.source != "system" or tag_id not in protected_ids
    )
    return Types.InternalTagChangesInfo(remove_ids=remove_ids, set_ids=set_ids)


def validate_internal_tag_removal(
    command: Types.ValidateInternalTagRemovalCommand,
) -> None:
    if command.source == "system" and any(
        link.tag_id == command.tag_id and link.source == "admin"
        for link in command.links
    ):
        raise ValueError("System cannot remove an administrator-assigned tag.")
