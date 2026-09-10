from typing import overload

from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.types import GenerationInfo


def message_entity_to_info(entity) -> Types.MessageInfo | None:
    if entity is None:
        return None
    return Types.MessageInfo(
        **{key: getattr(entity, key) for key in Types.MessageInfo.__dataclass_fields__}
    )


def messages_entities_to_page_info(
    entities, conversation_id, limit
) -> Types.MessagePageInfo:
    items = tuple(
        Types.MessageInfo(
            **{
                key: getattr(entity, key)
                for key in Types.MessageInfo.__dataclass_fields__
            }
        )
        for entity in entities[:limit]
    )
    cursor = (
        Types.MessageCursor(conversation_id, items[-1].position)
        if len(entities) > limit
        else None
    )
    return Types.MessagePageInfo(items, cursor)


def message_request_entity_to_info(entity) -> Types.MessageRequestInfo | None:
    return (
        None
        if entity is None
        else Types.MessageRequestInfo(entity.input_digest, entity.message_id)
    )


def generation_statistics_rows_to_info(rows) -> Types.GenerationStatisticsInfo:
    return Types.GenerationStatisticsInfo(
        *[[tuple(row) for row in group] for group in rows]
    )


def generation_record_to_info(
    run: ProductGeneration | Types.GenerationStateInfo, *, created: bool = False
) -> GenerationInfo:
    return GenerationInfo(
        id=run.id,
        created=created,
        status=run.status,
        product_snapshot_id=run.product_snapshot_id,
        model_id=run.model_id,
        model_name=run.model_name,
        reasoning_effort=run.reasoning_effort,
        message_count=run.message_count,
    )


@overload
def generation_entity_to_state_info(
    entity: ProductGeneration,
) -> Types.GenerationStateInfo: ...


@overload
def generation_entity_to_state_info(entity: None) -> None: ...


def generation_entity_to_state_info(
    entity: ProductGeneration | None,
) -> Types.GenerationStateInfo | None:
    if entity is None:
        return None
    return Types.GenerationStateInfo(
        **{
            key: getattr(entity, key)
            for key in Types.GenerationStateInfo.__dataclass_fields__
        }
    )
