from app.modules.content.tag import types as TagTypes


def public_tag_links_entities_to_info(entities):
    return tuple(
        TagTypes.PublicTagLinkInfo(
            row.tag_id, row.sort_order, row.assigned_by, row.created_at
        )
        for row in entities
    )


def internal_tag_links_entities_to_info(entities):
    return tuple(
        TagTypes.InternalTagLinkInfo(
            row.tag_id, row.source, row.assigned_by, row.created_at, row.updated_at
        )
        for row in entities
    )


def public_tag_links_infos_to_tags(links, tags):
    by_id = {tag.id: tag for tag in tags}
    return tuple(
        TagTypes.PublicTagInfo(
            link.tag_id,
            by_id[link.tag_id].name,
            by_id[link.tag_id].is_active,
            link.sort_order,
        )
        for link in links
    )


def internal_tag_links_infos_to_tags(links, tags):
    by_id = {tag.id: tag for tag in tags}
    return tuple(
        TagTypes.InternalTagInfo(
            link.tag_id,
            by_id[link.tag_id].name,
            by_id[link.tag_id].is_active,
            link.source,
            link.assigned_by,
            link.created_at,
            link.updated_at,
        )
        for link in links
    )
