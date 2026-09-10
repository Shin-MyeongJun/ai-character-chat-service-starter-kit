from datetime import UTC, datetime

from app.db.transaction import use_case_transaction
from app.modules.chatting.conversation import repository as Repository
from app.modules.chatting.conversation import types as Types
from app.modules.chatting.conversation.mapper import persistence as PersistenceMapper
from app.modules.chatting.conversation.service import get_owned_conversation
from app.modules.content.product import types as ProductTypes
from app.modules.content.product.service import query as ProductQueryService
from app.modules.content.product.service import views as ProductViewsService
from app.modules.content.product.service.command.statistics_queue import (
    mark_statistics_dirty,
)


async def switch_version(
    session, command: Types.SwitchVersionCommand
) -> Types.VersionSwitchedInfo:
    conversation_id = command.conversation_id
    user_id = command.user_id
    target_snapshot_id = command.target_snapshot_id
    automatic = command.automatic
    async with use_case_transaction(session):
        conversation = await get_owned_conversation(
            session,
            Types.OwnedConversationCommand(
                conversation_id=conversation_id, user_id=user_id, lock=True
            ),
        )
        if conversation.product_snapshot_id is None:
            raise ValueError("Legacy version is not verified.")
        if conversation.product_snapshot_id == target_snapshot_id:
            return Types.VersionSwitchedInfo(target_snapshot_id, False)
        current = await ProductQueryService.get_product_snapshot(
            session,
            ProductTypes.ProductSnapshotCommand(conversation.product_snapshot_id),
        )
        target = await ProductQueryService.get_product_snapshot(
            session, ProductTypes.ProductSnapshotCommand(target_snapshot_id)
        )
        if target.product_id != conversation.product_id:
            raise LookupError("Version not found.")
        await ProductQueryService.ensure_snapshot_available(
            session, ProductTypes.ProductSnapshotCommand(target.id)
        )
        if target.version <= current.version:
            raise ValueError("Only forward version transitions are supported.")
        notes = await ProductQueryService.list_product_releases(
            session,
            ProductTypes.ListProductReleasesCommand(
                product_id=conversation.product_id,
                after_version=current.version,
                through_version=target.version,
            ),
        )
        if not notes or any((n is None for _, n in notes)):
            raise ValueError("Release notes missing; transition unavailable.")
        if automatic and any(
            (n is None or n.update_policy != "automatic" for _, n in notes)
        ):
            raise ValueError("Customer consent required for this transition.")
        runtime = await ProductViewsService.get_snapshot_runtime(
            session, ProductTypes.ProductSnapshotCommand(target.id)
        )
        characters = runtime.composition.characters
        if not characters or sum(c.is_primary for c in characters) != 1:
            raise ValueError("Invalid target composition.")
        values = PersistenceMapper.snapshot_runtime_view_to_character_commands(runtime)
        changed_at = datetime.now(UTC)
        await Repository.switch_conversation_version(
            session,
            conversation.id,
            current.id,
            target.id,
            values,
            "automatic" if automatic else "choice",
            changed_at,
        )
        await mark_statistics_dirty(
            session,
            ProductTypes.MarkStatisticsDirtyCommand(
                conversation.product_id, changed_at
            ),
        )
        return Types.VersionSwitchedInfo(target.id, True)
