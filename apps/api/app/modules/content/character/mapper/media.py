from typing import overload

from app.db.models.character_media import CharacterMedia
from app.modules.content.character import types as Types


@overload
def media_entity_to_info(entity: CharacterMedia) -> Types.CharacterMediaInfo: ...


@overload
def media_entity_to_info(entity: None) -> None: ...


def media_entity_to_info(
    entity: CharacterMedia | None,
) -> Types.CharacterMediaInfo | None:
    if entity is None:
        return None
    return Types.CharacterMediaInfo(
        id=entity.id,
        character_id=entity.character_id,
        owner_id=entity.owner_id,
        request_id=entity.request_id,
        storage_kind=entity.storage_kind,
        storage_id=entity.storage_id,
        object_key=entity.object_key,
        content_type=entity.content_type,
        size_bytes=entity.size_bytes,
        original_filename=entity.original_filename,
        purpose=entity.purpose,
        sha256=entity.sha256,
        state=entity.state,
        binding=entity.binding,
        updated_at=entity.updated_at,
    )
