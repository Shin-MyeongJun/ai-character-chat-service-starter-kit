# 상품 구성 슬롯 ID와 원본 character ID를 구분해 참여자 값으로 옮긴다. runtime은 원본 대신 스냅샷 내용을 사용한다.
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import cast, overload
from uuid import UUID

from app.db.models.chat import Conversation, ConversationCharacter
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.repository import ConversationStatisticsRows
from app.modules.content.lorebook import types as LorebookTypes
from app.modules.content.product import types as ProductTypes
from app.modules.llm import types as LlmTypes


def conversation_characters_entities_to_infos(
    entities: Iterable[ConversationCharacter],
) -> tuple[Types.ConversationCharacterInfo, ...]:
    return tuple(
        Types.ConversationCharacterInfo(
            character.character_id, character.product_character_id, character.role_order
        )
        for character in entities
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
        id=entity.id,
        user_id=entity.user_id,
        product_id=entity.product_id,
        product_snapshot_id=entity.product_snapshot_id,
        initial_snapshot_id=entity.initial_snapshot_id,
        start_set_id=entity.start_set_id,
        created_at=entity.created_at,
        history_revision=entity.history_revision,
        opening_mode=entity.opening_mode,
    )


def conversations_entities_to_page_info(
    rows: Sequence[Conversation], limit: int
) -> Types.ConversationListPageInfo:
    selected = rows[:limit]
    items = tuple(
        Types.ConversationListItemInfo(
            id=row.id,
            product_id=row.product_id,
            title=row.title,
            created_at=row.created_at,
        )
        for row in selected
    )
    last = selected[-1] if len(rows) > limit else None
    return Types.ConversationListPageInfo(
        items, last.created_at if last else None, last.id if last else None
    )


def snapshot_runtime_view_to_character_commands(
    runtime: ProductTypes.SnapshotRuntimeView,
) -> tuple[Types.ConversationCharacterCommand, ...]:
    return tuple(
        Types.ConversationCharacterCommand(
            character_id=runtime.characters[
                character.character_snapshot_id
            ].character_id,
            product_character_id=character.id,
            role_order=character.role_order,
        )
        for character in runtime.composition.characters
    )


def snapshot_runtime_view_to_create_command(
    runtime: ProductTypes.SnapshotRuntimeView,
    snapshot: ProductTypes.ProductSnapshotInfo,
    user_id: UUID,
    product_id: UUID,
    start_set_id: UUID,
) -> Types.CreateConversationCommand:
    return Types.CreateConversationCommand(
        user_id=user_id,
        product_id=product_id,
        snapshot_id=snapshot.id,
        start_set_id=start_set_id,
        title=snapshot.snapshot_data["title"],
        characters=snapshot_runtime_view_to_character_commands(runtime),
    )


def conversation_snapshot_infos_to_runtime_view(
    conversation: Types.ConversationInfo,
    snapshot: ProductTypes.ProductSnapshotInfo,
    runtime: ProductTypes.SnapshotRuntimeView,
    execution: LlmTypes.ExecutionView,
    active_entries: Mapping[UUID, list[LorebookTypes.LorebookSnapshotEntryData]],
    start_context: Types.ConversationStartView,
) -> Types.ConversationRuntimeView:
    # Published snapshot fields and legacy extensions are JSON-compatible values;
    # TypedDict.items() otherwise erases this existing value contract to object.
    snapshot_data = cast(ProductTypes.ProductJsonObject, snapshot.snapshot_data)
    return Types.ConversationRuntimeView(
        execution=execution,
        product_snapshot_id=str(snapshot.id),
        settings={
            key: value
            for key, value in snapshot_data.items()
            if key not in {"opening_message", "studio_start_options"}
        },
        start=start_context.start,
        opening_message=start_context.opening_message,
        characters=[
            Types.RuntimeCharacter(
                id=str(character.id),
                snapshot_id=str(character.character_snapshot_id),
                primary=character.is_primary,
                data=runtime.characters[character.character_snapshot_id].snapshot_data,
            )
            for character in runtime.composition.characters
        ],
        lorebooks=[
            Types.RuntimeLorebook(
                id=str(lorebook.id),
                scope=lorebook.scope,
                targets=[
                    str(target.product_character_id)
                    for target in runtime.composition.targets
                    if target.product_lorebook_id == lorebook.id
                ],
                entries=active_entries[lorebook.lorebook_snapshot_id],
            )
            for lorebook in runtime.composition.books
        ],
    )


def conversation_statistics_rows_to_info(
    rows: ConversationStatisticsRows,
) -> Types.ConversationStatisticsInfo:
    conversations, transitions = rows
    counts: list[tuple[UUID, int]] = []
    for snapshot_id, count in conversations:
        # The repository's IS NOT NULL filter excludes legacy unverified starts.
        assert snapshot_id is not None
        counts.append((snapshot_id, count))
    return Types.ConversationStatisticsInfo(
        counts, [(snapshot_id, count) for snapshot_id, count in transitions]
    )


def conversation_start_infos_to_view(
    conversation: Types.ConversationInfo,
    initial: ProductTypes.ProductSnapshotInfo | None,
    start: ProductTypes.SnapshotStartInfo | None,
    participants: tuple[Types.ConversationCharacterInfo, ...],
    primary_id: UUID | None,
) -> Types.ConversationStartView:
    opening_message = None
    if initial is not None and conversation.opening_mode == "snapshot":
        # get_conversation_start rejects a missing start before calling this mapper.
        assert start is not None
        # The published studio options map source entry IDs to per-scene openings.
        # This describes the existing stored shape without coercing legacy JSON.
        options = cast(
            Mapping[str, Mapping[str, str | None]],
            initial.snapshot_data.get("studio_start_options", {}),
        )
        opening_message = options.get(str(start.source_entry_id), {}).get(
            "opening", initial.snapshot_data["opening_message"]
        )
    return Types.ConversationStartView(
        initial_snapshot_id=conversation.initial_snapshot_id,
        opening_mode=conversation.opening_mode,
        opening_message=opening_message,
        start=Types.RuntimeStart(start.title, start.content)
        if start is not None
        else None,
        participants=participants,
        primary_product_character_id=primary_id,
    )
