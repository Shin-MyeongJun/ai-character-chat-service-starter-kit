from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.content.product.service import views as ProductViewsService
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)


async def create_product_conversation(
    session, command: Types.StartConversationCommand
) -> Types.PreparedConversationInfo:
    product_id = command.product_id
    user_id = command.user_id
    start_set_id = command.start_set_id
    async with use_case_transaction(session):
        product = await ProductQueryService.get_accessible_product(
            session,
            ProductTypes.GetAccessibleProductCommand(
                product_id=product_id, user_id=user_id, lock=True
            ),
        )
        if not product.latest_snapshot_id:
            raise ValueError("Product has no published version.")
        snapshot = await ProductQueryService.ensure_snapshot_available(
            session, ProductTypes.ProductSnapshotCommand(product.latest_snapshot_id)
        )
        runtime = await ProductViewsService.get_snapshot_runtime(
            session, ProductTypes.ProductSnapshotCommand(snapshot.id)
        )
        starts = runtime.composition.starts
        if start_set_id is None and len(starts) == 1:
            start_set_id = starts[0].id
        if start_set_id not in {s.id for s in starts}:
            raise ValueError("Choose exactly one start option from this version.")
        primary = next(
            (c for c in runtime.composition.characters if c.is_primary), None
        )
        if primary is None:
            raise ValueError("Version has no primary character.")
        create_command = PersistenceMapper.snapshot_runtime_view_to_create_command(
            runtime, snapshot, user_id, product_id, start_set_id, primary
        )
        row = await Repository.create_conversation(session, create_command)
        conversation = PersistenceMapper.conversation_entity_to_info(row)
        await mark_statistics_dirty(
            session,
            ProductTypes.MarkStatisticsDirtyCommand(
                product_id, conversation.created_at
            ),
        )
        return Types.PreparedConversationInfo(
            Types.ConversationStartedInfo(conversation.id, snapshot.id, start_set_id),
            create_command.opening_message,
            create_command.primary_product_character_id,
        )
