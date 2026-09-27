"""Initial product start content and current participating characters."""

from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation.service import query as QueryService
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService


async def get_conversation_start(
    session, command: Types.OwnedConversationCommand
) -> Types.ConversationStartView:
    conversation = await QueryService.get_owned_conversation(session, command)
    participants = await QueryService.list_conversation_characters(session, command)
    initial, start, primary_id = None, None, None
    if conversation.initial_snapshot_id is not None:
        initial = await ProductQueryService.get_product_snapshot(
            session,
            ProductTypes.ProductSnapshotCommand(conversation.initial_snapshot_id),
        )
        composition = await ProductQueryService.get_snapshot_composition(
            session,
            ProductTypes.ProductSnapshotCommand(conversation.initial_snapshot_id),
        )
        start = next(
            (s for s in composition.starts if s.id == conversation.start_set_id), None
        )
        if start is None:
            raise ValueError("Initial start option is unavailable.")
    if conversation.product_snapshot_id is not None:
        current = await ProductQueryService.get_snapshot_composition(
            session,
            ProductTypes.ProductSnapshotCommand(conversation.product_snapshot_id),
        )
        primary_id = next((c.id for c in current.characters if c.is_primary), None)
        if primary_id not in {c.product_character_id for c in participants}:
            primary_id = None
    return PersistenceMapper.conversation_start_infos_to_view(
        conversation, initial, start, participants, primary_id
    )
