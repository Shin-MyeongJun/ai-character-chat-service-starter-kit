from collections.abc import Iterable

from app.http.contracts import tags as Schemas
from app.modules.content.tag import types as TagTypes


def internal_tag_infos_to_response(
    infos: Iterable[TagTypes.InternalTagInfo],
) -> list[Schemas.InternalTagResponseDto]:
    return [Schemas.InternalTagResponseDto.model_validate(info) for info in infos]


def tag_info_to_response(info: TagTypes.TagInfo) -> Schemas.TagResponseDto:
    return Schemas.TagResponseDto.model_validate(info)
