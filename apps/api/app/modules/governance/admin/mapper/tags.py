from app.http.contracts import tags as Schemas


def internal_tag_infos_to_response(infos):
    return [Schemas.InternalTagResponseDto.model_validate(info) for info in infos]


def tag_info_to_response(info):
    return Schemas.TagResponseDto.model_validate(info)
