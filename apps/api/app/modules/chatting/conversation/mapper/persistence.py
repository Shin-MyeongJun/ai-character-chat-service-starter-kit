from __future__ import annotations

from typing import overload

from app.db.models.chat import Conversation
from app.db.models.product_usage import ProductGeneration
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.types import GenerationInfo


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
def conversation_entity_to_info(entity: Conversation) -> Types.ConversationInfo: ...


@overload
def conversation_entity_to_info(entity: None) -> None: ...


def conversation_entity_to_info(
    entity: Conversation | None,
) -> Types.ConversationInfo | None:
    if entity is None:
        return None
    return Types.ConversationInfo(
        **{
            key: getattr(entity, key)
            for key in Types.ConversationInfo.__dataclass_fields__
        }
    )


def snapshot_runtime_view_to_character_commands(
    runtime,
) -> tuple[Types.ConversationCharacterCommand, ...]:
    return tuple(
        Types.ConversationCharacterCommand(
            runtime.characters[c.character_snapshot_id].character_id, c.id, c.role_order
        )
        for c in runtime.composition.characters
    )


def snapshot_runtime_view_to_create_command(
    runtime, snapshot, user_id, product_id, start_set_id, primary
) -> Types.CreateConversationCommand:
    return Types.CreateConversationCommand(
        user_id,
        product_id,
        snapshot.id,
        start_set_id,
        snapshot.snapshot_data["title"],
        snapshot.snapshot_data["opening_message"],
        runtime.characters[primary.character_snapshot_id].character_id,
        primary.id,
        snapshot_runtime_view_to_character_commands(runtime),
    )


def conversation_snapshot_infos_to_runtime_view(
    conversation, snapshot, runtime, execution, eligible_entries
) -> Types.ConversationRuntimeView:
    start = next(
        s for s in runtime.composition.starts if s.id == conversation.start_set_id
    )
    return Types.ConversationRuntimeView(
        execution=execution,
        product_snapshot_id=str(snapshot.id),
        settings=snapshot.snapshot_data,
        start=Types.RuntimeStart(title=start.title, content=start.content),
        characters=[
            Types.RuntimeCharacter(
                id=str(c.id),
                snapshot_id=str(c.character_snapshot_id),
                primary=c.is_primary,
                data=runtime.characters[c.character_snapshot_id].snapshot_data,
            )
            for c in runtime.composition.characters
        ],
        lorebooks=[
            Types.RuntimeLorebook(
                id=str(b.id),
                scope=b.scope,
                targets=[
                    str(t.product_character_id)
                    for t in runtime.composition.targets
                    if t.product_lorebook_id == b.id
                ],
                entries=eligible_entries[b.lorebook_snapshot_id],
            )
            for b in runtime.composition.books
        ],
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


def conversation_statistics_rows_to_info(rows) -> Types.ConversationStatisticsInfo:
    return Types.ConversationStatisticsInfo(
        *[[tuple(row) for row in group] for group in rows]
    )
