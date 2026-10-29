from collections.abc import Iterable
from uuid import UUID

from app.http.contracts import tags as Schemas
from app.modules.content.character import types as Types
from app.modules.content.tag import types as TagTypes


def public_tags_request_to_command(
    target_id: UUID,
    user_id: UUID,
    request: Schemas.TagsRequestDto,
) -> Types.PublicTagsCommand:
    return Types.PublicTagsCommand(
        target_id=target_id, user_id=user_id, names=tuple(request.tags)
    )


def internal_tags_request_to_command(
    target_id: UUID,
    actor_id: UUID,
    request: Schemas.TagsRequestDto,
) -> Types.InternalTagsCommand:
    return Types.InternalTagsCommand(
        target_id=target_id, actor_id=actor_id, names=tuple(request.tags)
    )


def public_tag_infos_to_response(
    infos: Iterable[TagTypes.PublicTagInfo],
) -> list[Schemas.PublicTagResponseDto]:
    return [Schemas.PublicTagResponseDto.model_validate(info) for info in infos]


def internal_tag_infos_to_response(
    infos: Iterable[TagTypes.InternalTagInfo],
) -> list[Schemas.InternalTagResponseDto]:
    return [Schemas.InternalTagResponseDto.model_validate(info) for info in infos]
