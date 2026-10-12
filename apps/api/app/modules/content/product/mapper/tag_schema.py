from app.http.contracts import tags as Schemas
from app.modules.content.product import types as Types


def public_tags_request_to_command(target_id, user_id, request):
    return Types.PublicTagsCommand(target_id, user_id, tuple(request.tags))


def internal_tags_request_to_command(target_id, actor_id, request):
    return Types.InternalTagsCommand(target_id, actor_id, tuple(request.tags))


def public_tag_infos_to_response(infos):
    return [Schemas.PublicTagResponseDto.model_validate(info) for info in infos]


def internal_tag_infos_to_response(infos):
    return [Schemas.InternalTagResponseDto.model_validate(info) for info in infos]
