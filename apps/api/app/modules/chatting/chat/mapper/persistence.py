# 조회 결과의 추가 한 행으로 다음 커서/원문 잘림을 계산한다. 생성 message_count는 최초 출력 수다.
from collections.abc import Iterable, Sequence
from typing import overload
from uuid import UUID

from app.db.models.chat import Message, MessageRequest
from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.chat import repository as Repository
from app.modules.chatting.chat import types as Types
from app.modules.chatting.chat.types import GenerationInfo


@overload
def message_entity_to_info(entity: Message) -> Types.MessageInfo: ...


@overload
def message_entity_to_info(entity: None) -> None: ...


def message_entity_to_info(entity: Message | None) -> Types.MessageInfo | None:
    if entity is None:
        return None
    return Types.MessageInfo(
        id=entity.id,
        conversation_id=entity.conversation_id,
        sender_type=entity.sender_type,
        content=entity.content,
        position=entity.position,
        revision=entity.revision,
        created_at=entity.created_at,
        character_id=entity.character_id,
        product_character_id=entity.product_character_id,
        product_snapshot_id=entity.product_snapshot_id,
        generation_id=entity.generation_id,
        generated_by_ai=entity.generated_by_ai,
        model_id=entity.model_id,
    )


def messages_entities_to_page_info(
    entities: Sequence[Message], conversation_id: UUID, limit: int
) -> Types.MessagePageInfo:
    items = tuple(message_entity_to_info(entity) for entity in entities[:limit])
    cursor = (
        Types.MessageCursor(conversation_id, items[-1].position)
        if len(entities) > limit
        else None
    )
    return Types.MessagePageInfo(items, cursor)


def conversation_preview_rows_to_info(
    rows: Iterable[Repository.ConversationPreviewRow],
) -> dict[UUID, str]:
    return {conversation_id: content for conversation_id, content in rows}


def conversation_activity_rows_to_info(
    rows: Iterable[Repository.ConversationActivityRow],
) -> dict[UUID, Types.ConversationActivityInfo]:
    """Detach message activity values so other modules never consume SQL rows."""
    return {
        conversation_id: Types.ConversationActivityInfo(content, created_at)
        for conversation_id, content, created_at in rows
    }


def messages_entities_to_memory_source_info(
    entities: Sequence[Message], limit: int
) -> Types.MemorySourceInfo:
    return Types.MemorySourceInfo(
        messages=tuple(message_entity_to_info(entity) for entity in entities[:limit]),
        truncated=len(entities) > limit,
    )


@overload
def message_request_entity_to_info(
    entity: MessageRequest,
) -> Types.MessageRequestInfo: ...


@overload
def message_request_entity_to_info(entity: None) -> None: ...


def message_request_entity_to_info(
    entity: MessageRequest | None,
) -> Types.MessageRequestInfo | None:
    return (
        None
        if entity is None
        else Types.MessageRequestInfo(entity.input_digest, entity.message_id)
    )


def generation_statistics_rows_to_info(
    rows: Repository.GenerationStatisticsRows,
) -> Types.GenerationStatisticsInfo:
    generation_rows, user_rows = rows
    return Types.GenerationStatisticsInfo(
        generations=[
            (snapshot_id, status, generation_count, message_count)
            for snapshot_id, status, generation_count, message_count in generation_rows
        ],
        users=[(snapshot_id, user_id) for snapshot_id, user_id in user_rows],
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
        id=entity.id,
        user_id=entity.user_id,
        conversation_id=entity.conversation_id,
        product_id=entity.product_id,
        product_snapshot_id=entity.product_snapshot_id,
        model_id=entity.model_id,
        model_name=entity.model_name,
        reasoning_effort=entity.reasoning_effort,
        request_key=entity.request_key,
        input_digest=entity.input_digest,
        result_digest=entity.result_digest,
        status=entity.status,
        message_count=entity.message_count,
        history_invalidated_at=entity.history_invalidated_at,
        answer_metadata=entity.answer_metadata,
        answer_lease_until=entity.answer_lease_until,
    )


def account_generation_statistics_rows_to_info(
    rows: Iterable[Repository.GenerationStatusCountRow],
) -> Types.AccountGenerationStatisticsInfo:
    """상태별 집계 행을 본인 생성 건수로 변환하고 실제 미기록 상태는 0건으로 표현한다."""
    counts_by_status = {status: count for status, count in rows}
    return Types.AccountGenerationStatisticsInfo(
        **{
            name: int(counts_by_status.get(name, 0))
            for name in ("pending", "succeeded", "failed", "cancelled", "stale")
        }
    )
